// Short plain-language guides (Learn page). General information only.

import type { Lang } from "./i18n";

export interface Guide {
  id: string;
  q: string;
  a: string[];
}

const en: Guide[] = [
  {
    id: "cash-price",
    q: "What is a cash price?",
    a: [
      "The price a hospital or provider charges people who pay for themselves instead of using insurance. It is often much lower than the full price, and sometimes lower than what an insurance plan pays.",
      "If you have a high deductible, paying the cash price can cost less than going through insurance. Ask whether a cash payment counts toward your deductible.",
    ],
  },
  {
    id: "list-price",
    q: "What is the \"full price\"?",
    a: [
      "Also called the \"gross charge\" or \"chargemaster\" price: the full price before any discount. Very few people pay it. Insurance plans and cash-paying patients usually pay less.",
    ],
  },
  {
    id: "plan-rate",
    q: "What is my plan's rate, and what will I owe?",
    a: [
      "Your insurance company agrees on a rate with each hospital. That rate is the total bill for your care. What you pay depends on your plan: your deductible (what you pay before insurance starts paying), then coinsurance (a percentage) or a copay (a set amount), up to your out-of-pocket maximum.",
      "Call the number on your insurance card for an estimate of your share.",
    ],
  },
  {
    id: "separate-bills",
    q: "Why might I get more than one bill?",
    a: [
      "The hospital or surgery center bills for the room, equipment and staff (the \"facility fee\"). Doctors, the anesthesia team, radiologists and labs often bill separately. Our whole-procedure estimates show which pieces have published prices and which don't.",
    ],
  },
  {
    id: "good-faith-estimate",
    q: "What is a Good Faith Estimate?",
    a: [
      "If you don't have insurance or won't use it, providers must give you a written estimate of expected charges when you schedule care at least 3 business days ahead, or when you ask. If the bill is at least $400 more than the estimate, you can dispute it within 120 days. Learn more at cms.gov/nosurprises.",
    ],
  },
  {
    id: "financial-assistance",
    q: "How does hospital financial assistance work?",
    a: [
      "Nonprofit hospitals must have a written financial assistance policy, and many other hospitals offer one. Most give free care below one income level and discounts up to a higher level, based on household size. Many people with insurance qualify too.",
      "You can usually apply before or after your care, often for months after the first bill. Ask for the application and have proof of income ready.",
    ],
  },
  {
    id: "surprise-bills",
    q: "Am I protected from surprise bills?",
    a: [
      "The federal No Surprises Act protects most people with insurance from surprise out-of-network bills for emergency care and for some care at in-network hospitals and surgery centers. If you think a bill breaks these rules, contact the No Surprises Help Desk at 1-800-985-3059.",
    ],
  },
];

const es: Guide[] = [
  {
    id: "cash-price",
    q: "¿Qué es un precio en efectivo?",
    a: [
      "El precio que un hospital o proveedor cobra a quienes pagan por su cuenta en lugar de usar un seguro. Suele ser mucho más bajo que el precio completo y a veces más bajo que lo que paga un plan de seguro.",
      "Si tiene un deducible alto, pagar en efectivo puede costar menos que usar el seguro. Pregunte si el pago en efectivo cuenta para su deducible.",
    ],
  },
  {
    id: "list-price",
    q: "¿Qué es el \"precio completo\"?",
    a: [
      "También llamado \"cargo bruto\": el precio completo antes de cualquier descuento. Muy poca gente lo paga. Los planes de seguro y quienes pagan en efectivo suelen pagar menos.",
    ],
  },
  {
    id: "plan-rate",
    q: "¿Qué es la tarifa de mi plan y cuánto pagaré?",
    a: [
      "Su aseguradora acuerda una tarifa con cada hospital. Esa tarifa es el total de la factura. Lo que usted paga depende de su plan: el deducible (lo que paga antes de que el seguro empiece a pagar), luego el coseguro (un porcentaje) o el copago (un monto fijo), hasta su máximo de gastos de bolsillo.",
      "Llame al número de su tarjeta de seguro para pedir un estimado de su parte.",
    ],
  },
  {
    id: "separate-bills",
    q: "¿Por qué podría recibir más de una factura?",
    a: [
      "El hospital o centro quirúrgico cobra el cuarto, el equipo y el personal (el \"cargo del centro\"). Los médicos, el equipo de anestesia, los radiólogos y los laboratorios a menudo cobran aparte. Nuestros estimados del procedimiento completo muestran qué partes tienen precio publicado y cuáles no.",
    ],
  },
  {
    id: "good-faith-estimate",
    q: "¿Qué es un Estimado de Buena Fe?",
    a: [
      "Si no tiene seguro o no lo va a usar, los proveedores deben darle un estimado por escrito cuando programa su atención con al menos 3 días hábiles de anticipación, o cuando lo pida. Si la factura supera el estimado en $400 o más, puede disputarla dentro de 120 días. Más información en cms.gov/nosurprises.",
    ],
  },
  {
    id: "financial-assistance",
    q: "¿Cómo funciona la ayuda financiera de los hospitales?",
    a: [
      "Los hospitales sin fines de lucro deben tener una política de ayuda financiera por escrito, y muchos otros hospitales ofrecen una. La mayoría da atención gratuita por debajo de cierto ingreso y descuentos hasta un nivel más alto, según el tamaño del hogar. Mucha gente con seguro también califica.",
      "Normalmente puede solicitar antes o después de su atención, a menudo durante meses después de la primera factura. Pida la solicitud y tenga a mano un comprobante de ingresos.",
    ],
  },
  {
    id: "surprise-bills",
    q: "¿Estoy protegido contra facturas sorpresa?",
    a: [
      "La ley federal No Surprises Act protege a la mayoría de las personas con seguro contra facturas sorpresa fuera de la red por atención de emergencia y por cierta atención en hospitales y centros quirúrgicos de la red. Si cree que una factura viola estas reglas, comuníquese con la línea de ayuda No Surprises al 1-800-985-3059.",
    ],
  },
];

export const GUIDES: Record<Lang, Guide[]> = { en, es };
