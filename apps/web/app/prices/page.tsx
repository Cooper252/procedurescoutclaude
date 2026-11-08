import { PlaceIndex } from "@/components/PlaceIndex";
import { ZipJump } from "@/components/ZipJump";
import * as data from "@/lib/server";

export const metadata = { title: "Medical prices by city and ZIP code" };

export default async function PricesIndex() {
  const sections = [];
  for (const [code, name] of Object.entries(data.STATES)) {
    const cs = await data.cities(code);
    sections.push({ heading: "areaCities" as const, vars: { state: name }, links: cs.map((c) => ({ href: `/prices/${code}/${c.slug}`, label: c.city })) });
  }
  return (
    <PlaceIndex title="areaBrowse" sections={sections}>
      <ZipJump />
    </PlaceIndex>
  );
}
