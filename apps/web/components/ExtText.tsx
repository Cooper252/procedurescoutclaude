import { Fragment } from "react";

// Government and nonprofit sites named in our text (HealthCare.gov,
// cms.gov/nosurprises...) become links that open in a new tab, so nobody has
// to type them (Cooper, 2026-11-12). Only .gov and .org names are linked.
const SITE = /\b((?:https?:\/\/)?(?:[a-z0-9-]+\.)+(?:gov|org)(?:\/[a-z0-9/_-]*[a-z0-9_-])?)/gi;

export function ExtText({ text }: { text: string }) {
  const parts = text.split(SITE);
  return (
    <>
      {parts.map((part, i) =>
        i % 2 === 1 ? (
          <a key={i} href={part.startsWith("http") ? part : `https://${part}`} target="_blank" rel="noopener noreferrer">
            {part.replace(/^https?:\/\//, "")}
          </a>
        ) : (
          <Fragment key={i}>{part}</Fragment>
        ),
      )}
    </>
  );
}
