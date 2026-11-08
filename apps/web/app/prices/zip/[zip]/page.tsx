import { notFound } from "next/navigation";
import { PlaceIndex } from "@/components/PlaceIndex";
import * as data from "@/lib/server";

type Params = Promise<{ zip: string }>;

export async function generateMetadata({ params }: { params: Params }) {
  const { zip } = await params;
  return { title: `Medical prices near ZIP ${zip}`, robots: data.PREVIEW ? { index: false, follow: false } : undefined };
}

export default async function ZipPage({ params }: { params: Params }) {
  const { zip } = await params;
  const p = await data.zip(zip);
  if (!p) notFound();
  const services = await data.services();
  return (
    <PlaceIndex
      title="areaZipTitle"
      vars={{ zip: p.zip }}
      sections={[{ heading: "areaServices", links: services.map((s) => ({ href: `/prices/zip/${p.zip}/${s.slug}`, label: s.name.replace(/ \(.*\)$/, ""), slug: s.slug })) }]}
    />
  );
}
