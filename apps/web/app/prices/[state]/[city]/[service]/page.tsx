import { notFound } from "next/navigation";
import { AreaPage, areaMetadata } from "@/components/AreaPage";
import * as data from "@/lib/server";

type Params = Promise<{ state: string; city: string; service: string }>;

export async function generateMetadata({ params }: { params: Params }) {
  const { state, city, service } = await params;
  const c = await data.city(state, city);
  if (!c) return { title: "Not found" };
  return areaMetadata(`${c.city}, ${c.state}`, c.lat, c.lng, service);
}

export default async function CityServicePage({ params }: { params: Params }) {
  const { state, city, service } = await params;
  const c = await data.city(state, city);
  if (!c) notFound();
  const others = (await data.cities(state)).filter((x) => x.slug !== c.slug).slice(0, 8);
  return (
    <AreaPage
      place={`${c.city}, ${c.state}`}
      lat={c.lat}
      lng={c.lng}
      serviceSlug={service}
      searchQuery={`lat=${c.lat}&lng=${c.lng}`}
      serviceHref={(s) => `/prices/${state}/${c.slug}/${s}`}
      nearby={others.map((x) => ({ href: `/prices/${state}/${x.slug}/${service}`, label: x.city }))}
    />
  );
}
