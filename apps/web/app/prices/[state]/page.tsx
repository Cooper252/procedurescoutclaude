import { notFound } from "next/navigation";
import { PlaceIndex } from "@/components/PlaceIndex";
import * as data from "@/lib/server";

type Params = Promise<{ state: string }>;

export async function generateMetadata({ params }: { params: Params }) {
  const { state } = await params;
  return { title: data.STATES[state] ? `Medical prices in ${data.STATES[state]}` : "Not found" };
}

export default async function StatePage({ params }: { params: Params }) {
  const { state } = await params;
  const name = data.STATES[state];
  if (!name) notFound();
  const cs = await data.cities(state);
  return (
    <PlaceIndex
      title="areaCities"
      vars={{ state: name }}
      sections={[{ heading: "areaBrowse", links: cs.map((c) => ({ href: `/prices/${state}/${c.slug}`, label: c.city })) }]}
    />
  );
}
