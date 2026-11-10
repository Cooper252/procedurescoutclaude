import { notFound } from "next/navigation";
import { PlaceIndex } from "@/components/PlaceIndex";
import * as data from "@/lib/server";

type Params = Promise<{ state: string; city: string }>;

export async function generateMetadata({ params }: { params: Params }) {
  const { state, city } = await params;
  const c = await data.city(state, city);
  return {
    title: c ? `Medical prices in ${c.city}, ${c.state}` : "Not found",
    robots: data.PREVIEW ? { index: false, follow: false } : undefined,
  };
}

export default async function CityPage({ params }: { params: Params }) {
  const { state, city } = await params;
  const c = await data.city(state, city);
  if (!c) notFound();
  const services = await data.services();
  const others = (await data.cities(state)).filter((x) => x.slug !== c.slug);
  return (
    <PlaceIndex
      title="cityTitle"
      vars={{ place: `${c.city}, ${c.state}` }}
      sections={[
        { heading: "areaServices", links: services.map((s) => ({ href: `/prices/${state}/${c.slug}/${s.slug}`, label: s.name.replace(/ \(.*\)$/, ""), slug: s.slug })) },
        { heading: "areaNearby", links: others.map((x) => ({ href: `/prices/${state}/${x.slug}`, label: x.city })) },
      ]}
    />
  );
}
