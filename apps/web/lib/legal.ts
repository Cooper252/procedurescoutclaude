// Disclaimer, terms of use and privacy notice, in plain words.
// DRAFT: must be reviewed by a lawyer before launch (docs/OPEN_QUESTIONS.md Q25).

import type { Lang } from "./i18n";

export interface LegalDoc {
  title: string;
  updated: string;
  intro: string;
  sections: { h: string; p: string[] }[];
}

type Docs = Record<"disclaimer" | "terms" | "privacy", LegalDoc>;

const en: Docs = {
  disclaimer: {
    title: "Disclaimer",
    updated: "Draft, November 2026. Pending legal review.",
    intro: "Please read this before relying on any price or result on ProcedureScout.",
    sections: [
      {
        h: "Prices are published information, not quotes",
        p: [
          "Hospital prices come from the machine-readable files hospitals are required to publish under federal price transparency rules. Provider prices are entered by the provider. We show them as published and do not change them.",
          "A price on this site is not a quote, an offer, a bill or a guarantee. Your actual cost can be different because of your diagnosis, the care you actually receive, separate charges from doctors, anesthesia, labs, imaging or supplies, your insurance plan's deductible, copay and coinsurance, and changes made after the file was published.",
          "Always confirm the price and what it includes with the provider before you receive care.",
        ],
      },
      {
        h: "Your right to a Good Faith Estimate",
        p: [
          "If you don't have insurance or choose not to use it, providers must give you a written Good Faith Estimate when you schedule care or ask for one. If your bill is at least $400 more than the estimate, you may be able to dispute it. See cms.gov/nosurprises.",
        ],
      },
      {
        h: "Free and reduced-cost care results",
        p: [
          "Our free-care check compares the income and household size you enter with each hospital's published financial assistance policy and the federal poverty guidelines. It is not an application and not a decision. Only the hospital decides who qualifies, and hospitals may count income, assets and household members differently.",
        ],
      },
      {
        h: "Not medical, legal or financial advice",
        p: [
          "ProcedureScout is not a healthcare provider, insurer, lender or referral service, and does not recommend any provider or treatment. Talk to your doctor about what care you need. In an emergency, call 911 or go to the nearest emergency room.",
        ],
      },
      {
        h: "Provider listings",
        p: [
          "Providers who list prices are verified before their prices appear, but verification does not mean we endorse them or guarantee their care. Paid listings are labeled, and payment never changes the order of results, badges or labels. ProcedureScout never takes deposits or payments for care.",
        ],
      },
      {
        h: "Errors",
        p: [
          "Published files sometimes contain mistakes. We flag prices that look wrong, but we cannot catch every error. If you see a price that seems wrong, tell us and we will review it.",
        ],
      },
    ],
  },
  terms: {
    title: "Terms of use",
    updated: "Draft, November 2026. Pending legal review.",
    intro: "By using ProcedureScout you agree to these terms. If you don't agree, please don't use the site.",
    sections: [
      {
        h: "What the site is for",
        p: [
          "ProcedureScout helps you compare published prices for medical care and see whether you may qualify for financial assistance. It is free for patients and needs no account.",
          "The information is provided \"as is\" for general information only. See the Disclaimer for the limits of the prices and results shown.",
        ],
      },
      {
        h: "Acceptable use",
        p: [
          "Don't misuse the site: no automated scraping that harms the service, no attempts to break security, and no false reports or reviews.",
        ],
      },
      {
        h: "Providers",
        p: [
          "Providers who list on ProcedureScout must be verified, must post real prices they honor, must not take deposits or payments through their listing, and must keep their information accurate. We may remove any listing that misleads patients. Separate provider terms will apply to provider accounts and paid listings.",
        ],
      },
      {
        h: "Limitation of liability",
        p: [
          "To the extent the law allows, ProcedureScout is not liable for decisions made using the site, for differences between published and actual prices, or for the care any provider gives.",
        ],
      },
      {
        h: "Changes",
        p: ["We may update these terms. The date at the top shows the latest version."],
      },
    ],
  },
  privacy: {
    title: "Privacy",
    updated: "Draft, November 2026. Pending legal review.",
    intro: "We built ProcedureScout to work without collecting personal information about patients.",
    sections: [
      {
        h: "What we don't collect",
        p: [
          "No account is needed. We don't ask for your name, insurance ID or medical history. We don't sell or share information about you, and we don't use advertising trackers.",
        ],
      },
      {
        h: "Your free-care answers",
        p: [
          "The household size and income you enter are used only to run the check you asked for. They stay in your browser while you use the site and are never put in web addresses or saved by us.",
        ],
      },
      {
        h: "Location",
        p: [
          "If you tap \"Use my location\", your browser asks first. We use an approximate location (about half a mile) only to find places near you. You can always type a ZIP code instead.",
        ],
      },
      {
        h: "What your browser remembers",
        p: ["Your language choice is saved on your own device so the site opens in that language next time."],
      },
      {
        h: "Basic service logs",
        p: [
          "Like most websites, our servers keep short-lived technical logs (such as which page was requested) to keep the service secure and working. We count searches in total, never by person.",
        ],
      },
      {
        h: "Providers",
        p: [
          "Provider accounts collect the business and contact details needed for verification. These are used only to verify and manage the listing.",
        ],
      },
    ],
  },
};

const es: Docs = {
  disclaimer: {
    title: "Aviso legal",
    updated: "Borrador, noviembre de 2026. Pendiente de revisión legal.",
    intro: "Lea esto antes de confiar en cualquier precio o resultado de ProcedureScout.",
    sections: [
      {
        h: "Los precios son información publicada, no cotizaciones",
        p: [
          "Los precios de los hospitales provienen de los archivos que la ley federal de transparencia de precios les exige publicar. Los precios de los proveedores los ingresa el proveedor. Los mostramos tal como se publicaron, sin cambiarlos.",
          "Un precio en este sitio no es una cotización, una oferta, una factura ni una garantía. Su costo real puede ser diferente según su diagnóstico, la atención que reciba, los cargos aparte de médicos, anestesia, laboratorio, imágenes o suministros, el deducible, copago y coseguro de su plan, y los cambios posteriores a la publicación del archivo.",
          "Confirme siempre el precio y lo que incluye con el proveedor antes de recibir atención.",
        ],
      },
      {
        h: "Su derecho a un Estimado de Buena Fe",
        p: [
          "Si no tiene seguro o decide no usarlo, los proveedores deben darle un Estimado de Buena Fe por escrito al programar su atención o cuando lo pida. Si su factura supera el estimado en $400 o más, podría disputarla. Visite cms.gov/nosurprises.",
        ],
      },
      {
        h: "Resultados de atención gratuita o a menor costo",
        p: [
          "Nuestra verificación compara el ingreso y el tamaño del hogar que usted ingresa con la política de ayuda financiera publicada por cada hospital y las guías federales de pobreza. No es una solicitud ni una decisión. Solo el hospital decide quién califica, y los hospitales pueden contar los ingresos, los bienes y los miembros del hogar de otra manera.",
        ],
      },
      {
        h: "No es consejo médico, legal ni financiero",
        p: [
          "ProcedureScout no es un proveedor de salud, aseguradora, prestamista ni servicio de referidos, y no recomienda ningún proveedor ni tratamiento. Hable con su médico sobre la atención que necesita. En una emergencia, llame al 911 o vaya a la sala de emergencias más cercana.",
        ],
      },
      {
        h: "Perfiles de proveedores",
        p: [
          "Los proveedores que publican precios se verifican antes de que aparezcan sus precios, pero la verificación no significa que los respaldemos ni que garanticemos su atención. Los perfiles pagados están marcados, y el pago nunca cambia el orden de los resultados, las insignias ni las etiquetas. ProcedureScout nunca cobra depósitos ni pagos por atención.",
        ],
      },
      {
        h: "Errores",
        p: [
          "Los archivos publicados a veces tienen errores. Marcamos los precios que parecen equivocados, pero no podemos detectarlos todos. Si ve un precio que parece incorrecto, avísenos y lo revisaremos.",
        ],
      },
    ],
  },
  terms: {
    title: "Términos de uso",
    updated: "Borrador, noviembre de 2026. Pendiente de revisión legal.",
    intro: "Al usar ProcedureScout usted acepta estos términos. Si no los acepta, no use el sitio.",
    sections: [
      {
        h: "Para qué sirve el sitio",
        p: [
          "ProcedureScout le ayuda a comparar precios publicados de atención médica y a ver si podría calificar para ayuda financiera. Es gratis para los pacientes y no necesita cuenta.",
          "La información se ofrece \"tal cual\", solo como información general. Vea el Aviso legal para conocer los límites de los precios y resultados.",
        ],
      },
      {
        h: "Uso aceptable",
        p: ["No haga mal uso del sitio: nada de extracción automática que dañe el servicio, intentos de violar la seguridad, ni reportes o reseñas falsas."],
      },
      {
        h: "Proveedores",
        p: [
          "Los proveedores que publican en ProcedureScout deben estar verificados, publicar precios reales que respeten, no cobrar depósitos ni pagos a través de su perfil y mantener su información al día. Podemos eliminar cualquier perfil que engañe a los pacientes. Las cuentas de proveedores y los perfiles pagados tendrán términos aparte.",
        ],
      },
      {
        h: "Limitación de responsabilidad",
        p: [
          "En la medida que la ley lo permita, ProcedureScout no es responsable de las decisiones tomadas con el sitio, de las diferencias entre precios publicados y reales, ni de la atención que dé cualquier proveedor.",
        ],
      },
      {
        h: "Cambios",
        p: ["Podemos actualizar estos términos. La fecha de arriba muestra la versión más reciente."],
      },
    ],
  },
  privacy: {
    title: "Privacidad",
    updated: "Borrador, noviembre de 2026. Pendiente de revisión legal.",
    intro: "Creamos ProcedureScout para que funcione sin recopilar información personal de los pacientes.",
    sections: [
      {
        h: "Lo que no recopilamos",
        p: [
          "No necesita cuenta. No pedimos su nombre, número de seguro ni historial médico. No vendemos ni compartimos información sobre usted, y no usamos rastreadores de publicidad.",
        ],
      },
      {
        h: "Sus respuestas sobre atención gratuita",
        p: [
          "El tamaño del hogar y el ingreso que ingresa se usan solo para la verificación que pidió. Se quedan en su navegador mientras usa el sitio; nunca se ponen en direcciones web ni los guardamos.",
        ],
      },
      {
        h: "Ubicación",
        p: [
          "Si toca \"Usar mi ubicación\", su navegador le pregunta primero. Usamos una ubicación aproximada (cerca de media milla) solo para encontrar lugares cercanos. Siempre puede escribir un código postal.",
        ],
      },
      {
        h: "Lo que recuerda su navegador",
        p: ["Su idioma se guarda en su propio dispositivo para que el sitio abra en ese idioma la próxima vez."],
      },
      {
        h: "Registros básicos del servicio",
        p: [
          "Como la mayoría de los sitios, nuestros servidores guardan registros técnicos de corta duración (por ejemplo, qué página se pidió) para mantener el servicio seguro y funcionando. Contamos las búsquedas en total, nunca por persona.",
        ],
      },
      {
        h: "Proveedores",
        p: ["Las cuentas de proveedores recopilan los datos del negocio y de contacto necesarios para la verificación. Se usan solo para verificar y administrar el perfil."],
      },
    ],
  },
};

export const LEGAL: Record<Lang, Docs> = { en, es };
