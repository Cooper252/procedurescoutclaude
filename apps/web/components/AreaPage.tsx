// Server side of a service-by-place page: fetches prices near the place and
// adds structured data for search engines. Prices are only ever the published
// ones the API returns; nothing is estimated for the page.

import { notFound } from "next/navigation";
import { costAnswer } from "@/lib/area";
import * as data from "@/lib/server";
import { AreaView, type AreaLink } from "./AreaView";

export const RADIUS = "25";

export async function AreaPage({
  place,
  lat,
  lng,
  serviceSlug,
  searchQuery,
  serviceHref,
  nearby,
}: {
  place: string;
  lat: string;
  lng: string;
  serviceSlug: string;
  searchQuery: string;
  serviceHref: (slug: string) => string;
  nearby: AreaLink[];
}) {
  const services = await data.services();
  const svc = services.find((s) => s.slug === serviceSlug);
  if (!svc) notFound();
  const result = await data.search(lat, lng, serviceSlug, RADIUS);
  const faq = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: [
      {
        "@type": "Question",
        name: `How much does ${svc.name} cost in ${place}?`,
        acceptedAnswer: { "@type": "Answer", text: costAnswer(result, place) },
      },
    ],
  };
  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(faq).replace(/</g, "\\u003c") }} />
      <AreaView
        place={place}
        serviceSlug={svc.slug}
        serviceName={svc.name}
        result={result}
        radius={RADIUS}
        searchHref={`/search?service=${svc.slug}&${searchQuery}`}
        otherServices={services
          .filter((s) => s.slug !== svc.slug)
          .slice(0, 12)
          .map((s) => ({ href: serviceHref(s.slug), label: s.name.replace(/ \(.*\)$/, ""), slug: s.slug }))}
        nearby={nearby}
      />
    </>
  );
}

export async function areaMetadata(place: string, lat: string, lng: string, serviceSlug: string) {
  const services = await data.services();
  const svc = services.find((s) => s.slug === serviceSlug);
  if (!svc) return { title: "Not found" };
  const result = await data.search(lat, lng, serviceSlug, RADIUS);
  return {
    title: `${svc.name} prices in ${place}`,
    description: `${costAnswer(result, place)} Compare hospitals and clinics, and see if you qualify for free or reduced-cost care.`,
    robots: data.PREVIEW ? { index: false, follow: false } : undefined,
  };
}
