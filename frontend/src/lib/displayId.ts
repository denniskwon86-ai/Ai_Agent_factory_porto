/**
 * 화면에 **식별자를 보여 줄 때**의 단일 규칙.
 *
 * ## ⚠️⚠️ 왜 필요한가 (2026-08-24 사용자 지적)
 *
 * > `sh_a111029126ae` 이런 객체 ID 들이 화면에 자꾸 노출된다.
 *
 * 맞다. `ki_6b06ffb50a994a` · `ds_0315a90335a444` 같은 값은 사용자에게 **아무 뜻도
 * 없다.** 그런데 완전히 지우면 안 된다 — 같은 종류가 여럿일 때 구분해야 하고, 문의할 때
 * 그 값으로 찾는다.
 *
 * ★ 그래서 **줄여서 보여 주고 전체 값은 `title` 로 남긴다.** 마우스를 올리면 원래 값이
 *   보이고, 복사도 된다.
 * ⚠️ 사람이 지은 이름(`smart-life-app`·`TEST1001-copy_20260713_171902`)은 **건드리지
 *   않는다.** 그것은 사용자가 직접 정한 값이라 오히려 그대로 보여야 한다.
 *   (서버 쪽 같은 규칙: `core/enterprise_briefing._readable`)
 */

/** 접두사 뒤가 긴 16진수 — 사람이 읽을 수 없는 값. */
const OPAQUE = /^(?:[a-z][a-z0-9]*_)*[0-9a-f]{8,}$/i;

/** 이 값이 사람에게 아무 뜻도 없는 해시인가. */
export function isOpaqueId(value: string | null | undefined): boolean {
  return OPAQUE.test(String(value ?? '').trim());
}

/**
 * 화면에 쓸 짧은 형태. 사람이 지은 이름은 그대로 돌려준다.
 *
 * ★ 함께 `title={원래 값}` 을 붙일 것 — 줄인 값만 남기면 문의할 때 찾을 수 없다.
 */
export function shortId(value: string | null | undefined, tail = 6): string {
  const raw = String(value ?? '').trim();
  if (!raw || !OPAQUE.test(raw)) return raw;
  const parts = raw.split('_');
  const head = parts.length > 1 ? parts.slice(0, -1).join('_') + '_' : '';
  return `${head}…${parts[parts.length - 1].slice(-tail)}`;
}
