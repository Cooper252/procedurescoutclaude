"use client";

// Finishes sign-in from the emailed link (#token, never sent to server logs).

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useApp } from "@/components/AppState";
import { portalText } from "@/lib/i18n_portal";
import { portal } from "@/lib/portal";

export default function VerifySignIn() {
  const { lang } = useApp();
  const p = portalText(lang);
  const router = useRouter();
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const token = window.location.hash.slice(1);
    history.replaceState(null, "", window.location.pathname);
    if (!token) {
      setFailed(true);
      return;
    }
    portal
      .verify(token)
      .then(() => router.replace("/providers/account"))
      .catch(() => setFailed(true));
  }, [router]);

  return (
    <div className="wrap page signin-wrap">
      <div className="card signin">
        {failed ? (
          <>
            <p className="notice">{p.verifyFailed}</p>
            <Link className="btn primary" href="/providers/sign-in">
              {p.newLink}
            </Link>
          </>
        ) : (
          <p className="loading">{p.verifying}</p>
        )}
      </div>
    </div>
  );
}
