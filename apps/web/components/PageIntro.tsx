import type { ReactNode } from "react";

// Teal top section for inner pages, matching the home page (Cooper chose the
// bold teal look, 2026-11-14). Content below it stays on the light background.
export function PageIntro(props: {
  eyebrow?: ReactNode;
  title: ReactNode;
  lead?: ReactNode;
  narrow?: boolean;
  children?: ReactNode;
}) {
  return (
    <section className="page-intro">
      <div className={props.narrow ? "wrap page-intro-in narrow" : "wrap page-intro-in"}>
        {props.eyebrow && <p className="eyebrow">{props.eyebrow}</p>}
        <h1 className="page-title">{props.title}</h1>
        {props.lead && <p className="lead">{props.lead}</p>}
        {props.children}
      </div>
    </section>
  );
}
