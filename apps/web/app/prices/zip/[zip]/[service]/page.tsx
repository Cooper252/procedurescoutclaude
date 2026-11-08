import { notFound } from "next/navigation";
import { AreaPage, areaMetadata } from "@/components/AreaPage";
import * as data from "@/lib/server";

type Params = Promise<{ zip: string; service: string }>;

export async function generateMetadata({ params }: { params: Params }) {
  const { zip, service } = await params;
  const p = await data.zip(zip);
  if (!p) return { title: "Not found" };
  return areaMetadata(`ZIP ${p.zip}`, p.lat, p.lng, service);
}

export default async function ZipServicePage({ params }: { params: Params }) {
  const { zip, service } = await params;
  const p = await data.zip(zip);
  if (!p) notFound();
  const st = p.state.toLowerCase();
  const near = (await data.cities(st)).slice(0, 8);
  return (
    <AreaPage
      place={`ZIP ${p.zip}`}
      lat={p.lat}
      lng={p.lng}
      serviceSlug={service}
      searchQuery={`zip=${p.zip}`}
      serviceHref={(s) => `/prices/zip/${p.zip}/${s}`}
      nearby={near.map((x) => ({ href: `/prices/${st}/${x.slug}/${service}`, label: x.city }))}
    />
  );
}
