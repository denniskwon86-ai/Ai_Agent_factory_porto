"""승인된 Windows 로컬 PG 환경 전용. 운영 배포/제품 스키마 설치 도구가 아니다.

setup은 새 환경만 만든다. 재실행/기존 자산 덮어쓰기/자동 삭제는 하지 않는다.
run은 같은 Windows 사용자의 DPAPI 비밀을 자식 AFS_DB_DSN으로만 전달한다.
비밀 보관은 같은 PC/사용자 전용이며 Git 이관 대상이 아니다.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time

DOCKER = r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"
NAME = "afs-pg-local"
VOLUME = "afs-pg-local-data"
DB = "afs_trial_local"
PORT = 55432
PRIVATE = Path(os.environ.get("LOCALAPPDATA", "")) / "AFS" / "pg-trial-local"
ROLES = {"installer": "afs_installer", "runtime": "afs_runtime"}


def command(args, **kwargs):
    result = subprocess.run(args, capture_output=True, text=True, timeout=90, **kwargs)
    if result.returncode:
        # 호출 인자/원문 stderr에는 비밀이 있을 수 있다.
        raise RuntimeError("외부 명령 실패; 비밀 보호를 위해 원문 출력 생략")
    return result.stdout.strip()


def docker(*args):
    return command([DOCKER, *args])


def crypt(data: bytes, decrypt=False) -> bytes:
    """Windows 사용자 DPAPI. UI prompt 없이 현재 사용자로만 암복호화."""
    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source, target = Blob(len(data), buffer), Blob()
    api = ctypes.WinDLL("crypt32", use_last_error=True)
    fn = api.CryptUnprotectData if decrypt else api.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                   ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise RuntimeError("DPAPI 실패")
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        free = ctypes.WinDLL("kernel32").LocalFree
        free.argtypes, free.restype = [ctypes.c_void_p], ctypes.c_void_p
        free(target.data)


def dsn(user, password):
    from psycopg.conninfo import make_conninfo
    return make_conninfo(host="127.0.0.1", port=PORT, dbname=DB, user=user,
                         password=password, connect_timeout=5, sslmode="disable",
                         options="-c search_path=app")


def role_dsn(role):
    password = crypt((PRIVATE / (role + ".dpapi")).read_bytes(), True).decode()
    return dsn(ROLES[role], password)


def setup():
    import psycopg
    from psycopg import sql
    if PRIVATE.exists():
        raise RuntimeError("비밀 보관 경로가 이미 있음; 재생성 금지")
    if NAME in docker("ps", "-a", "--format", "{{.Names}}").splitlines():
        raise RuntimeError("컨테이너 이름 충돌")
    if VOLUME in docker("volume", "ls", "--format", "{{.Name}}").splitlines():
        raise RuntimeError("볼륨 이름 충돌")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", PORT))
    image = json.loads(docker("image", "inspect", "postgres:16"))[0]
    digest = image["RepoDigests"][0]
    if not digest.startswith("postgres@sha256:"):
        raise RuntimeError("공식 postgres 이미지 digest 불일치")
    # 새 비공개 폴더만 만든다. 기존 부모 junction을 따라 쓰지 않는다.
    for parent in (PRIVATE, *PRIVATE.parents):
        if parent.is_symlink() or (hasattr(parent, "is_junction") and parent.is_junction()):
            raise RuntimeError("비밀 경로의 링크 거절")
    PRIVATE.mkdir(parents=True)
    import csv
    sid = next(csv.reader([command(["whoami", "/user", "/fo", "csv", "/nh"])]))[1]
    command(["icacls", str(PRIVATE), "/inheritance:r", "/grant:r", f"*{sid}:(OI)(CI)F"])
    admin = secrets.token_urlsafe(36)
    passwords = {role: secrets.token_urlsafe(36) for role in ROLES}
    # 관리자 초기화 파일만 Docker에 readonly로 제공. 소스/운영 경로 mount 없음.
    secret_file = PRIVATE / "admin.password"
    secret_file.write_text(admin, encoding="ascii")
    for role, password in passwords.items():
        (PRIVATE / (role + ".dpapi")).write_bytes(crypt(password.encode()))
    docker("volume", "create", "--label", "afs.purpose=local-pg-trial", VOLUME)
    docker("run", "-d", "--name", NAME, "--label", "afs.purpose=local-pg-trial",
           "--restart", "no", "--cpus", "2", "--memory", "1g",
           "-p", f"127.0.0.1:{PORT}:5432",
           "--mount", f"type=volume,source={VOLUME},target=/var/lib/postgresql/data",
           "--mount", f"type=bind,source={secret_file},target=/run/secrets/pg-admin,readonly",
           "-e", "POSTGRES_PASSWORD_FILE=/run/secrets/pg-admin",
           "-e", "POSTGRES_HOST_AUTH_METHOD=scram-sha-256", "-e", f"POSTGRES_DB={DB}",
           digest)
    (PRIVATE / "metadata.json").write_text(json.dumps({"image": digest, "container": NAME,
        "volume": VOLUME, "database": DB, "port": PORT}, indent=2), encoding="utf-8")
    admin_dsn = dsn("postgres", admin)
    for _ in range(25):
        try:
            conn = psycopg.connect(admin_dsn)
            break
        except psycopg.OperationalError:
            time.sleep(1)
    else:
        raise RuntimeError("PG 기동 시간 초과; 생성 자산은 보존됨")
    with conn:
        # 실패 시 비밀번호 포함 DDL 원문이 서버 로그에 남지 않게 한다.
        conn.execute("SET log_statement = 'none'")
        conn.execute("SET log_min_error_statement = 'panic'")
        for role, user in ROLES.items():
            conn.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER "
                "NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT").format(
                    sql.Identifier(user), sql.Literal(passwords[role])))
        conn.execute("REVOKE ALL ON DATABASE afs_trial_local FROM PUBLIC")
        conn.execute("GRANT CONNECT ON DATABASE afs_trial_local TO afs_installer, afs_runtime")
        conn.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
        conn.execute("CREATE SCHEMA app AUTHORIZATION afs_installer")
        conn.execute("REVOKE ALL ON SCHEMA app FROM PUBLIC")
        conn.execute("GRANT USAGE ON SCHEMA app TO afs_runtime")
        conn.execute("ALTER DEFAULT PRIVILEGES FOR ROLE afs_installer IN SCHEMA app "
                     "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO afs_runtime")
        conn.execute("ALTER DEFAULT PRIVILEGES FOR ROLE afs_installer IN SCHEMA app "
                     "GRANT USAGE, SELECT ON SEQUENCES TO afs_runtime")
        conn.execute("ALTER DEFAULT PRIVILEGES FOR ROLE afs_installer "
                     "REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC")
        for user in ROLES.values():
            conn.execute(sql.SQL("ALTER ROLE {} IN DATABASE afs_trial_local SET search_path TO app")
                         .format(sql.Identifier(user)))
    check()


def check():
    import psycopg
    info = json.loads(docker("inspect", NAME))[0]
    assert info["State"]["Running"]
    assert info["HostConfig"]["PortBindings"] == {
        "5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(PORT)}]}
    mounts = info["Mounts"]
    assert len(mounts) == 2
    assert any(m["Type"] == "volume" and m["Name"] == VOLUME for m in mounts)
    assert any(m["Type"] == "bind" and not m["RW"] and
               m["Destination"] == "/run/secrets/pg-admin" for m in mounts)
    report = {"container": NAME, "binding": f"127.0.0.1:{PORT}", "roles": {}}
    for role in ROLES:
        with psycopg.connect(role_dsn(role)) as conn:
            row = conn.execute("SELECT current_database(), current_schema(), current_user, "
                               "current_setting('server_version')").fetchone()
            assert row[:3] == (DB, "app", ROLES[role])
            report["version"] = row[3]
            assert 160000 <= int(conn.execute("SHOW server_version_num").fetchone()[0]) < 170000
            report["roles"][role] = row[:3]
    with psycopg.connect(role_dsn("runtime")) as conn:
        privileges = conn.execute("SELECT has_database_privilege(current_user,current_database(),'CREATE'), "
            "has_database_privilege(current_user,current_database(),'TEMP'), "
            "has_schema_privilege(current_user,'app','CREATE'), "
            "has_schema_privilege(current_user,'public','CREATE'), "
            "pg_has_role(current_user,'afs_installer','MEMBER')").fetchone()
        assert privileges == (False,) * 5
        flags = conn.execute("SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls "
                             "FROM pg_roles WHERE rolname=current_user").fetchone()
        assert flags == (False,) * 5
    denied = []
    for statement in ("CREATE TABLE app._env_probe(id int)",
                      "CREATE TEMP TABLE _env_probe(id int)",
                      "CREATE SCHEMA _env_probe", "SET ROLE afs_installer"):
        with psycopg.connect(role_dsn("runtime")) as conn:
            try:
                conn.execute(statement)
            except psycopg.errors.InsufficientPrivilege:
                denied.append(True)
            else:
                raise RuntimeError("runtime 권한 경계 실패")
            finally:
                conn.rollback()
    report["runtime_denied_probes"] = len(denied)
    report["product_acceptance"] = "NOT_ASSESSED"  # 환경 점검은 제품 수용이 아니다.
    print(json.dumps(report, ensure_ascii=False, indent=2))


def main():
    if os.name != "nt":
        raise RuntimeError("이 도구는 승인된 Windows 로컬 환경 전용")
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("setup")
    sub.add_parser("check")
    run = sub.add_parser("run")
    run.add_argument("role", choices=ROLES)
    run.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.action == "setup":
        setup()
    elif args.action == "check":
        check()
    else:
        child = args.command
        if child[:1] == ["--"]:
            child = child[1:]
        if not child:
            parser.error("실행할 자식 명령 필요")
        env = dict(os.environ, AFS_DB_DSN=role_dsn(args.role), AFS_DB_BACKEND="postgres")
        return subprocess.call(child, env=env)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("local_pg_trial 실패: " + type(exc).__name__ +
              " (비밀 보호: 예외 원문 생략, 자산 자동 삭제 없음)", file=sys.stderr)
        sys.exit(1)
