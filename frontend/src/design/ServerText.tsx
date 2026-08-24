/**
 * 서버가 준 **문장**을 화면에 그린다.
 *
 * ## ⚠️⚠️ 왜 필요한가 (2026-08-24 사용자 지적)
 *
 * 서버 문구는 `**같은 자료**` 처럼 굵게 쓰려는 표시를 담고 있는데, 화면은 그것을
 * 평문으로 찍었다. 그래서 사용자에게는 **별표가 글자로** 보였다 —
 * 「두 방식이 \*\*서로 다른 자료로\*\* 돌아서…」.
 *
 * `core/` 전체에서 이런 문자열이 25곳 있었다. 문자열을 하나씩 고치면 새로 쓰는 사람이
 * 또 같은 표기를 쓴다 — 표기가 잘못된 게 아니라 **그리는 쪽이 안 읽고 있었다.**
 * 그래서 그리는 자리 하나에서 처리한다.
 *
 * ★ `innerHTML` 을 쓰지 않는다 — 서버 문구를 HTML 로 해석하면 그 문구가 곧 주입 경로가
 *   된다. 노드를 직접 만든다.
 * ⚠️ 굵게 말고는 아무것도 해석하지 않는다. 링크·이미지까지 열면 서버 문구가 화면 구조를
 *   바꿀 수 있게 되고, 그때는 「문구를 고쳤을 뿐」이 화면 사고가 된다.
 */
import { Fragment, type ReactNode } from 'react';

/** `**굵게**` 만 해석한다. 나머지는 글자 그대로. */
export function renderServerText(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  const src = String(text ?? '');
  //: 짝이 맞는 `**…**` 만 굵게 — 홀수 개면 그냥 글자로 남긴다(깨진 표기를 숨기지 않는다).
  const re = /\*\*([^*]+)\*\*/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let key = 0;
  while ((m = re.exec(src)) !== null) {
    if (m.index > last) out.push(<Fragment key={key++}>{src.slice(last, m.index)}</Fragment>);
    out.push(<b key={key++}>{m[1]}</b>);
    last = m.index + m[0].length;
  }
  if (last < src.length) out.push(<Fragment key={key++}>{src.slice(last)}</Fragment>);
  return out;
}

/**
 * 서버 문장 한 덩이.
 *
 * ★ `text` 가 비면 **아무것도 그리지 않는다** — 빈 상자를 남기면 「내용이 없다」와
 *   「불러오지 못했다」가 같아 보인다. 그 구분은 부르는 쪽이 한다.
 */
export function ServerText({ text, className, style }: {
  text: string | null | undefined;
  className?: string;
  style?: React.CSSProperties;
}) {
  const s = String(text ?? '').trim();
  if (!s) return null;
  return <span className={className} style={style}>{renderServerText(s)}</span>;
}
