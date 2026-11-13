// State laws that limit hospital bills or require free care, shown on Help
// paying for the person's state. Each one is from the state's own statute,
// regulation or agency page (linked as `source`), checked by Claude under D-056
// on 2026-11-12. General information, not legal advice.

export interface StateLaw {
  title: [string, string]; // English, Spanish
  body: [string, string];
  fine: [string, string];
  source: string;
}

export const STATE_LAWS: Record<string, StateLaw> = {
  NV: {
    title: ["Nevada law: 30% off for some uninsured hospital stays", "Ley de Nevada: 30% de descuento en algunas hospitalizaciones sin seguro"],
    body: [
      "If you stay in a Nevada hospital as an inpatient, have no insurance, and don't qualify for Medicaid or another public program, a large private hospital must cut your bill by at least 30%. You must make reasonable arrangements to pay within 30 days of the notice that comes with your first bill.",
      "Si usted está internado en un hospital de Nevada, no tiene seguro y no califica para Medicaid u otro programa público, un hospital privado grande debe rebajar su factura al menos un 30%. Debe hacer arreglos razonables de pago dentro de los 30 días del aviso que llega con su primera factura.",
    ],
    fine: [
      "Private hospitals with 200 or more beds (alone or with affiliated hospitals in the same county); not government hospitals or outpatient visits. Nevada Revised Statutes 439B.260 and 439B.115. Disputes go to Nevada's Bureau for Hospital Patients.",
      "Hospitales privados con 200 camas o más (solos o con hospitales afiliados en el mismo condado); no hospitales del gobierno ni visitas ambulatorias. Estatutos Revisados de Nevada 439B.260 y 439B.115. Las disputas van a la Oficina para Pacientes de Hospitales de Nevada.",
    ],
    source: "https://www.leg.state.nv.us/NRS/NRS-439B.html#NRS439BSec260",
  },
  CA: {
    title: ["California law: hospital bills capped for many patients", "Ley de California: límite en facturas de hospital para muchos pacientes"],
    body: [
      "If you're uninsured or have high medical costs and your household income is at or below 400% of the federal poverty level, a California hospital must offer free or discounted care, and can't expect more than it would get from Medicare or Medi-Cal, whichever is more.",
      "Si no tiene seguro o tiene gastos médicos altos y el ingreso de su hogar es igual o menor al 400% del nivel federal de pobreza, un hospital de California debe ofrecer atención gratuita o con descuento, y no puede esperar cobrar más de lo que recibiría de Medicare o Medi-Cal, lo que sea mayor.",
    ],
    fine: [
      "Hospital Fair Pricing Act, Health and Safety Code § 127400 and following (§ 127405). Rural hospitals may set lower income levels. Hospitals can't report these bills to credit bureaus.",
      "Ley de Precios Justos de Hospitales, Código de Salud y Seguridad § 127400 y siguientes (§ 127405). Los hospitales rurales pueden fijar niveles de ingreso más bajos. Los hospitales no pueden reportar estas facturas a las agencias de crédito.",
    ],
    source: "https://hcai.ca.gov/affordability/hospital-fair-billing-program/laws-and-regulations",
  },
  NY: {
    title: ["New York law: free or low-cost hospital care up to 400% of poverty", "Ley de Nueva York: atención de hospital gratuita o de bajo costo hasta el 400% de la pobreza"],
    body: [
      "If you're uninsured or underinsured with household income at or below 400% of the federal poverty level, most New York hospitals must waive charges under 200%, and charge at most 10% (200 to 300%) or 20% (301 to 400%) of what Medicaid would pay, or of what your plan would make you pay.",
      "Si no tiene seguro o tiene seguro insuficiente y el ingreso de su hogar es igual o menor al 400% del nivel federal de pobreza, la mayoría de los hospitales de Nueva York deben perdonar los cargos por debajo del 200%, y cobrar como máximo el 10% (200 a 300%) o el 20% (301 a 400%) de lo que pagaría Medicaid, o de lo que su plan le haría pagar.",
    ],
    fine: [
      "Public Health Law § 2807-k(9-a). Payment plans can't exceed 5% of monthly income. Non-emergency care may be limited to the hospital's service area.",
      "Ley de Salud Pública § 2807-k(9-a). Los planes de pago no pueden superar el 5% del ingreso mensual. La atención que no es de emergencia puede limitarse al área de servicio del hospital.",
    ],
    source: "https://ag.ny.gov/resources/individuals/health-care-insurance/hospital-financial-assistance",
  },
  NJ: {
    title: ["New Jersey law: uninsured hospital bills capped near Medicare rates", "Ley de Nueva Jersey: facturas de hospital sin seguro limitadas cerca de las tarifas de Medicare"],
    body: [
      "If you're an uninsured New Jersey resident with family income under 500% of the federal poverty level, a New Jersey hospital can charge you no more than 115% of what Medicare pays.",
      "Si es residente de Nueva Jersey sin seguro y el ingreso de su familia es menor al 500% del nivel federal de pobreza, un hospital de Nueva Jersey no puede cobrarle más del 115% de lo que paga Medicare.",
    ],
    fine: ["N.J.S.A. 26:2H-12.52. New Jersey's separate charity care program can cover more.", "N.J.S.A. 26:2H-12.52. El programa de atención caritativa de Nueva Jersey puede cubrir más."],
    source: "https://law.justia.com/codes/new-jersey/title-26/section-26-2h-12-52/",
  },
  IL: {
    title: ["Illinois law: discounts for uninsured hospital patients", "Ley de Illinois: descuentos para pacientes de hospital sin seguro"],
    body: [
      "If you're uninsured, Illinois hospitals must give free care at or below 200% of the federal poverty level (125% at rural and critical access hospitals) and a discount up to 600% (300% at rural hospitals). The most they can collect in a year is 20% of your family's income.",
      "Si no tiene seguro, los hospitales de Illinois deben dar atención gratuita si su ingreso es igual o menor al 200% del nivel federal de pobreza (125% en hospitales rurales y de acceso crítico) y un descuento hasta el 600% (300% en hospitales rurales). Lo máximo que pueden cobrar en un año es el 20% del ingreso de su familia.",
    ],
    fine: ["Hospital Uninsured Patient Discount Act, 210 ILCS 89/10. You must apply. Hospitals may consider some assets.", "Ley de Descuentos para Pacientes sin Seguro, 210 ILCS 89/10. Debe solicitarlo. Los hospitales pueden considerar algunos bienes."],
    source: "https://ilga.gov/legislation/ilcs/documents/021000890K10.htm",
  },
  CO: {
    title: ["Colorado law: Hospital Discounted Care", "Ley de Colorado: Atención Hospitalaria con Descuento"],
    body: [
      "Low-income Colorado patients can get hospital care charged at about Medicare or Medicaid rates (whichever is more), with payments capped at 4% of monthly income for hospital bills and 2% for doctors' bills. After 36 months of payments, the rest is forgiven.",
      "Los pacientes de bajos ingresos en Colorado pueden recibir atención hospitalaria cobrada a tarifas parecidas a las de Medicare o Medicaid (la que sea mayor), con pagos limitados al 4% del ingreso mensual en facturas del hospital y al 2% en facturas de médicos. Después de 36 meses de pagos, se perdona el resto.",
    ],
    fine: ["Colorado Hospital Discounted Care (HB21-1198), for households up to 250% of the federal poverty level. Hospitals must screen uninsured patients.", "Atención Hospitalaria con Descuento de Colorado (HB21-1198), para hogares de hasta el 250% del nivel federal de pobreza. Los hospitales deben evaluar a los pacientes sin seguro."],
    source: "https://hcpf.colorado.gov/hospital-discounted-care",
  },
  MD: {
    title: ["Maryland law: free hospital care up to 200% of poverty", "Ley de Maryland: atención de hospital gratuita hasta el 200% de la pobreza"],
    body: [
      "Maryland hospitals must give free medically necessary care at or below 200% of the federal poverty level, and cut what you owe by 75% (201 to 250%) or 60% (251 to 300%). With medical debt over 25% of income, discounts continue up to 500%.",
      "Los hospitales de Maryland deben dar atención médicamente necesaria gratuita si su ingreso es igual o menor al 200% del nivel federal de pobreza, y reducir lo que debe en un 75% (201 a 250%) o un 60% (251 a 300%). Con deudas médicas mayores al 25% del ingreso, hay descuentos hasta el 500%.",
    ],
    fine: ["Health-General Article § 19-214.1.", "Artículo de Salud-General § 19-214.1."],
    source: "https://mgaleg.maryland.gov/2026RS/Statute_Web/ghg/19-214.1.pdf",
  },
  WA: {
    title: ["Washington law: free hospital care up to 300% of poverty at most hospitals", "Ley de Washington: atención de hospital gratuita hasta el 300% de la pobreza en la mayoría de los hospitales"],
    body: [
      "At larger Washington hospitals, care is free up to 300% of the federal poverty level, 75% off up to 350% and 50% off up to 400%. At other hospitals: free up to 200%, 75% off up to 250%, 50% off up to 300%. Insurance status doesn't matter.",
      "En los hospitales grandes de Washington, la atención es gratuita hasta el 300% del nivel federal de pobreza, con 75% de descuento hasta el 350% y 50% hasta el 400%. En otros hospitales: gratuita hasta el 200%, 75% de descuento hasta el 250%, 50% hasta el 300%. No importa si tiene seguro.",
    ],
    fine: ["RCW 70.170.060. Hospitals may reduce the 75% and 50% discounts based on assets.", "RCW 70.170.060. Los hospitales pueden reducir los descuentos del 75% y 50% según sus bienes."],
    source: "https://lawfilesext.leg.wa.gov/Law/RCWPDF/RCW%20%2070%20%20TITLE/RCW%20%2070%20.170%20%20CHAPTER/RCW%20%2070%20.170%20.060.pdf",
  },
  OR: {
    title: ["Oregon law: free care at nonprofit hospitals up to 200% of poverty", "Ley de Oregón: atención gratuita en hospitales sin fines de lucro hasta el 200% de la pobreza"],
    body: [
      "Oregon nonprofit hospitals must cut your costs by 100% up to 200% of the federal poverty level, at least 75% up to 300%, 50% up to 350% and 25% up to 400%. They can't make you apply for Medicaid first.",
      "Los hospitales sin fines de lucro de Oregón deben reducir sus costos en un 100% hasta el 200% del nivel federal de pobreza, al menos un 75% hasta el 300%, 50% hasta el 350% y 25% hasta el 400%. No pueden exigirle que solicite Medicaid primero.",
    ],
    fine: ["ORS 442.614. Also covers the hospital's nonprofit clinics.", "ORS 442.614. También cubre las clínicas sin fines de lucro del hospital."],
    source: "https://oregon.public.law/statutes/ors_442.614",
  },
  CT: {
    title: ["Connecticut law: low-income uninsured patients pay no more than cost", "Ley de Connecticut: pacientes sin seguro de bajos ingresos no pagan más que el costo"],
    body: [
      "If you're uninsured, can't get public coverage, and your income is below 250% of the federal poverty level, a Connecticut hospital can't collect more than the cost of providing your care.",
      "Si no tiene seguro, no puede obtener cobertura pública y su ingreso es menor al 250% del nivel federal de pobreza, un hospital de Connecticut no puede cobrar más del costo de su atención.",
    ],
    fine: ["Connecticut General Statutes § 19a-673. Hospitals can't report medical bills to credit bureaus (§ 19a-673b).", "Estatutos Generales de Connecticut § 19a-673. Los hospitales no pueden reportar facturas médicas a las agencias de crédito (§ 19a-673b)."],
    source: "https://portal.ct.gov/oha/knowledge-base/articles/health-insurance/medical-bills-and-debt/medical-debt-rules-in-connecticut",
  },
  VT: {
    title: ["Vermont law: free hospital care up to 250% of poverty", "Ley de Vermont: atención de hospital gratuita hasta el 250% de la pobreza"],
    body: [
      "At large Vermont hospitals, uninsured residents get free care at or below 250% of the federal poverty level and at least 40% off up to 400%. Insured residents at or below 250% owe nothing out of pocket. Up to 600%, bills over 20% of household income are cut to 20%.",
      "En los hospitales grandes de Vermont, los residentes sin seguro reciben atención gratuita si su ingreso es igual o menor al 250% del nivel federal de pobreza y al menos 40% de descuento hasta el 400%. Los residentes con seguro hasta el 250% no pagan nada de su bolsillo. Hasta el 600%, las facturas mayores al 20% del ingreso del hogar se reducen al 20%.",
    ],
    fine: ["18 V.S.A. § 9482. Vermont residents, with no minimum time living in the state.", "18 V.S.A. § 9482. Residentes de Vermont, sin un tiempo mínimo viviendo en el estado."],
    source: "https://legislature.vermont.gov/statutes/section/18/221/09482",
  },
  RI: {
    title: ["Rhode Island rule: free hospital care up to 200% of poverty", "Regla de Rhode Island: atención de hospital gratuita hasta el 200% de la pobreza"],
    body: [
      "Rhode Island hospitals must give free care to uninsured, low-income residents at or below 200% of the federal poverty level, and a sliding-scale discount between 200% and 300%.",
      "Los hospitales de Rhode Island deben dar atención gratuita a residentes sin seguro y de bajos ingresos con ingreso igual o menor al 200% del nivel federal de pobreza, y un descuento según escala entre el 200% y el 300%.",
    ],
    fine: ["216-RICR-40-10-23.14. For residents not eligible for public or employer coverage. Each hospital sets its own sliding scale.", "216-RICR-40-10-23.14. Para residentes que no califican para cobertura pública o del empleador. Cada hospital fija su propia escala."],
    source: "https://rules.sos.ri.gov/regulations/part/216-40-10-23",
  },
  ME: {
    title: ["Maine law: free hospital care up to 200% of poverty", "Ley de Maine: atención de hospital gratuita hasta el 200% de la pobreza"],
    body: [
      "Maine hospitals must give free medically necessary care to residents with family income at or below 200% of the federal poverty level, and offer payment plans up to 400% with payments of no more than 4% of monthly income.",
      "Los hospitales de Maine deben dar atención médicamente necesaria gratuita a residentes con ingreso familiar igual o menor al 200% del nivel federal de pobreza, y ofrecer planes de pago hasta el 400% con pagos de no más del 4% del ingreso mensual.",
    ],
    fine: ["22 M.R.S. § 1716-A. Maine residents (not visitors).", "22 M.R.S. § 1716-A. Residentes de Maine (no visitantes)."],
    source: "https://legislature.maine.gov/statutes/22/title22sec1716-A.html",
  },
  NM: {
    title: ["New Mexico law: no medical debt collection for low-income patients", "Ley de Nuevo México: no se cobran deudas médicas a pacientes de bajos ingresos"],
    body: [
      "If your household income is at or below 200% of the federal poverty level, hospitals and other providers in New Mexico can't take collection actions against you for medical bills, such as suing, selling the debt, garnishing wages or placing a lien.",
      "Si el ingreso de su hogar es igual o menor al 200% del nivel federal de pobreza, los hospitales y otros proveedores de Nuevo México no pueden tomar acciones de cobro por facturas médicas, como demandarlo, vender la deuda, embargar su salario o poner un gravamen.",
    ],
    fine: ["Patients' Debt Collection Protection Act (2021, SB 71). You can show you qualify with the state's Attestation of Indigency form.", "Ley de Protección contra el Cobro de Deudas de Pacientes (2021, SB 71). Puede demostrar que califica con el formulario estatal de Declaración de Indigencia."],
    source: "https://www.osi.state.nm.us/en/consumer-assistance/patients-debt-collection-protection-act/",
  },
  MA: {
    title: ["Massachusetts: the Health Safety Net pays hospital bills", "Massachusetts: la Red de Seguridad de Salud paga facturas de hospital"],
    body: [
      "Massachusetts residents with income up to 150% of the federal poverty level can have hospital and community health center care paid in full by the Health Safety Net; from 150% to 300% it pays after a deductible. Doctors who bill separately are often not covered.",
      "Los residentes de Massachusetts con ingreso de hasta el 150% del nivel federal de pobreza pueden tener la atención en hospitales y centros de salud comunitarios pagada por completo por la Red de Seguridad de Salud; entre el 150% y el 300% paga después de un deducible. Los médicos que cobran aparte a menudo no están cubiertos.",
    ],
    fine: ["Apply through the hospital's or health center's financial counselor (the MassHealth application).", "Solicítelo con el consejero financiero del hospital o centro de salud (la solicitud de MassHealth)."],
    source: "https://www.mass.gov/info-details/health-safety-net-for-patients",
  },
  MN: {
    title: ["Minnesota law: uninsured patients charged no more than insurers pay", "Ley de Minnesota: a pacientes sin seguro no se les cobra más de lo que pagan las aseguradoras"],
    body: [
      "If you're uninsured and your household income is under $125,000 a year, a Minnesota hospital can't charge you more than the lowest total it would get from a private insurer for the same care.",
      "Si no tiene seguro y el ingreso de su hogar es menor a $125,000 al año, un hospital de Minnesota no puede cobrarle más que el total más bajo que recibiría de una aseguradora privada por la misma atención.",
    ],
    fine: ["Minnesota Statutes § 144.589. Enforced by the Department of Health and the Attorney General.", "Estatutos de Minnesota § 144.589. Lo hacen cumplir el Departamento de Salud y el Fiscal General."],
    source: "https://www.revisor.mn.gov/statutes/2024/cite/144.589",
  },
};
