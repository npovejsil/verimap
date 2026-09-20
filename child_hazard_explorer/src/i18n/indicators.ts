import { HAZARD_LABELS, HAZARD_MEASURE } from "../data/hazard";
import type { Locale } from "./index";

/**
 * Indicator names and hazard-measure names by language.
 *
 * Machine-translated, not reviewed by a speaker. Anything missing falls back to
 * the English tables in `src/data/hazard.ts`, so a partial translation shows
 * mixed language rather than a bare indicator code.
 */
type ByCode = Record<string, string>;

const INDICATORS: Partial<Record<Locale, ByCode>> = {
  fr: {
    AGRICULTURAL_STRESS: "Stress agricole", COASTAL_FLOOD: "Submersion côtière",
    COMPLEX_EMERGENCIES_ACLED: "Urgences complexes", EARTHQUAKE_0P09: "Séisme (0,09 g)",
    EARTHQUAKE_0P34: "Séisme (0,34 g)", EXTREME_HOT_DAYS: "Journées très chaudes",
    FIRE_FREQUENCY: "Fréquence des incendies", FIRE_INTENSITY: "Intensité des incendies",
    HEATWAVE_DURATION: "Durée des canicules", HEATWAVE_FREQUENCY: "Fréquence des canicules",
    HEATWAVE_SEVERITY: "Sévérité des canicules", LANDSLIDES_0P01: "Glissements (0,01)",
    LANDSLIDES_0P1: "Glissements (0,1)", MALARIA_FALCIPARUM: "Paludisme (P. falciparum)",
    MALARIA_VIVAX: "Paludisme (P. vivax)", METEOROLOGICAL_DROUGHT_SPEI: "Sécheresse (SPEI)",
    METEOROLOGICAL_DROUGHT_SPI: "Sécheresse (SPI)", PM25: "Pollution de l'air (PM2,5)",
    RIVER_FLOOD: "Crue fluviale", SDS_SUSCEPTIBILITY: "Tempêtes de sable et poussière",
    VOLCANOES_100KM_BUFFER: "Volcans (100 km)", WIND_SPEED: "Vents extrêmes",
  },
  es: {
    AGRICULTURAL_STRESS: "Estrés agrícola", COASTAL_FLOOD: "Inundación costera",
    COMPLEX_EMERGENCIES_ACLED: "Emergencias complejas", EARTHQUAKE_0P09: "Terremoto (0,09 g)",
    EARTHQUAKE_0P34: "Terremoto (0,34 g)", EXTREME_HOT_DAYS: "Días de calor extremo",
    FIRE_FREQUENCY: "Frecuencia de incendios", FIRE_INTENSITY: "Intensidad de incendios",
    HEATWAVE_DURATION: "Duración de olas de calor", HEATWAVE_FREQUENCY: "Frecuencia de olas de calor",
    HEATWAVE_SEVERITY: "Severidad de olas de calor", LANDSLIDES_0P01: "Deslizamientos (0,01)",
    LANDSLIDES_0P1: "Deslizamientos (0,1)", MALARIA_FALCIPARUM: "Malaria (P. falciparum)",
    MALARIA_VIVAX: "Malaria (P. vivax)", METEOROLOGICAL_DROUGHT_SPEI: "Sequía (SPEI)",
    METEOROLOGICAL_DROUGHT_SPI: "Sequía (SPI)", PM25: "Contaminación del aire (PM2,5)",
    RIVER_FLOOD: "Inundación fluvial", SDS_SUSCEPTIBILITY: "Tormentas de arena y polvo",
    VOLCANOES_100KM_BUFFER: "Volcanes (100 km)", WIND_SPEED: "Viento extremo",
  },
  pt: {
    AGRICULTURAL_STRESS: "Stress agrícola", COASTAL_FLOOD: "Inundação costeira",
    COMPLEX_EMERGENCIES_ACLED: "Emergências complexas", EARTHQUAKE_0P09: "Sismo (0,09 g)",
    EARTHQUAKE_0P34: "Sismo (0,34 g)", EXTREME_HOT_DAYS: "Dias de calor extremo",
    FIRE_FREQUENCY: "Frequência de incêndios", FIRE_INTENSITY: "Intensidade de incêndios",
    HEATWAVE_DURATION: "Duração das ondas de calor", HEATWAVE_FREQUENCY: "Frequência das ondas de calor",
    HEATWAVE_SEVERITY: "Severidade das ondas de calor", LANDSLIDES_0P01: "Deslizamentos (0,01)",
    LANDSLIDES_0P1: "Deslizamentos (0,1)", MALARIA_FALCIPARUM: "Malária (P. falciparum)",
    MALARIA_VIVAX: "Malária (P. vivax)", METEOROLOGICAL_DROUGHT_SPEI: "Seca (SPEI)",
    METEOROLOGICAL_DROUGHT_SPI: "Seca (SPI)", PM25: "Poluição do ar (PM2,5)",
    RIVER_FLOOD: "Cheia fluvial", SDS_SUSCEPTIBILITY: "Tempestades de areia e poeira",
    VOLCANOES_100KM_BUFFER: "Vulcões (100 km)", WIND_SPEED: "Vento extremo",
  },
  id: {
    AGRICULTURAL_STRESS: "Tekanan pertanian", COASTAL_FLOOD: "Banjir pesisir",
    COMPLEX_EMERGENCIES_ACLED: "Darurat kompleks", EARTHQUAKE_0P09: "Gempa (0,09 g)",
    EARTHQUAKE_0P34: "Gempa (0,34 g)", EXTREME_HOT_DAYS: "Hari sangat panas",
    FIRE_FREQUENCY: "Frekuensi kebakaran", FIRE_INTENSITY: "Intensitas kebakaran",
    HEATWAVE_DURATION: "Durasi gelombang panas", HEATWAVE_FREQUENCY: "Frekuensi gelombang panas",
    HEATWAVE_SEVERITY: "Keparahan gelombang panas", LANDSLIDES_0P01: "Longsor (0,01)",
    LANDSLIDES_0P1: "Longsor (0,1)", MALARIA_FALCIPARUM: "Malaria (P. falciparum)",
    MALARIA_VIVAX: "Malaria (P. vivax)", METEOROLOGICAL_DROUGHT_SPEI: "Kekeringan (SPEI)",
    METEOROLOGICAL_DROUGHT_SPI: "Kekeringan (SPI)", PM25: "Polusi udara (PM2,5)",
    RIVER_FLOOD: "Banjir sungai", SDS_SUSCEPTIBILITY: "Badai pasir dan debu",
    VOLCANOES_100KM_BUFFER: "Gunung api (100 km)", WIND_SPEED: "Angin ekstrem",
  },
  zh: {
    AGRICULTURAL_STRESS: "农业胁迫", COASTAL_FLOOD: "沿海洪水",
    COMPLEX_EMERGENCIES_ACLED: "复杂紧急状况", EARTHQUAKE_0P09: "地震（0.09g）",
    EARTHQUAKE_0P34: "地震（0.34g）", EXTREME_HOT_DAYS: "极端高温日",
    FIRE_FREQUENCY: "火灾频率", FIRE_INTENSITY: "火灾强度",
    HEATWAVE_DURATION: "热浪持续时间", HEATWAVE_FREQUENCY: "热浪频率",
    HEATWAVE_SEVERITY: "热浪强度", LANDSLIDES_0P01: "滑坡（0.01）",
    LANDSLIDES_0P1: "滑坡（0.1）", MALARIA_FALCIPARUM: "疟疾（恶性疟原虫）",
    MALARIA_VIVAX: "疟疾（间日疟原虫）", METEOROLOGICAL_DROUGHT_SPEI: "干旱（SPEI）",
    METEOROLOGICAL_DROUGHT_SPI: "干旱（SPI）", PM25: "空气污染（PM2.5）",
    RIVER_FLOOD: "河流洪水", SDS_SUSCEPTIBILITY: "沙尘暴",
    VOLCANOES_100KM_BUFFER: "火山（100 公里）", WIND_SPEED: "极端风速",
  },
  ru: {
    AGRICULTURAL_STRESS: "Агрострессы", COASTAL_FLOOD: "Прибрежные наводнения",
    COMPLEX_EMERGENCIES_ACLED: "Комплексные чрезвычайные ситуации", EARTHQUAKE_0P09: "Землетрясение (0,09 g)",
    EARTHQUAKE_0P34: "Землетрясение (0,34 g)", EXTREME_HOT_DAYS: "Дни экстремальной жары",
    FIRE_FREQUENCY: "Частота пожаров", FIRE_INTENSITY: "Интенсивность пожаров",
    HEATWAVE_DURATION: "Продолжительность волн жары", HEATWAVE_FREQUENCY: "Частота волн жары",
    HEATWAVE_SEVERITY: "Сила волн жары", LANDSLIDES_0P01: "Оползни (0,01)",
    LANDSLIDES_0P1: "Оползни (0,1)", MALARIA_FALCIPARUM: "Малярия (P. falciparum)",
    MALARIA_VIVAX: "Малярия (P. vivax)", METEOROLOGICAL_DROUGHT_SPEI: "Засуха (SPEI)",
    METEOROLOGICAL_DROUGHT_SPI: "Засуха (SPI)", PM25: "Загрязнение воздуха (PM2,5)",
    RIVER_FLOOD: "Речные наводнения", SDS_SUSCEPTIBILITY: "Песчаные и пыльные бури",
    VOLCANOES_100KM_BUFFER: "Вулканы (100 км)", WIND_SPEED: "Экстремальный ветер",
  },
  ar: {
    AGRICULTURAL_STRESS: "الإجهاد الزراعي", COASTAL_FLOOD: "الفيضان الساحلي",
    COMPLEX_EMERGENCIES_ACLED: "حالات الطوارئ المعقدة", EARTHQUAKE_0P09: "زلزال (0.09 g)",
    EARTHQUAKE_0P34: "زلزال (0.34 g)", EXTREME_HOT_DAYS: "أيام الحر الشديد",
    FIRE_FREQUENCY: "تواتر الحرائق", FIRE_INTENSITY: "شدة الحرائق",
    HEATWAVE_DURATION: "مدة موجات الحر", HEATWAVE_FREQUENCY: "تواتر موجات الحر",
    HEATWAVE_SEVERITY: "شدة موجات الحر", LANDSLIDES_0P01: "الانهيارات الأرضية (0.01)",
    LANDSLIDES_0P1: "الانهيارات الأرضية (0.1)", MALARIA_FALCIPARUM: "الملاريا (المنجلية)",
    MALARIA_VIVAX: "الملاريا (النشيطة)", METEOROLOGICAL_DROUGHT_SPEI: "الجفاف (SPEI)",
    METEOROLOGICAL_DROUGHT_SPI: "الجفاف (SPI)", PM25: "تلوث الهواء (PM2.5)",
    RIVER_FLOOD: "فيضان الأنهار", SDS_SUSCEPTIBILITY: "العواصف الرملية والترابية",
    VOLCANOES_100KM_BUFFER: "البراكين (100 كم)", WIND_SPEED: "الرياح الشديدة",
  },
  hi: {
    AGRICULTURAL_STRESS: "कृषि तनाव", COASTAL_FLOOD: "तटीय बाढ़",
    COMPLEX_EMERGENCIES_ACLED: "जटिल आपात स्थितियाँ", EARTHQUAKE_0P09: "भूकंप (0.09g)",
    EARTHQUAKE_0P34: "भूकंप (0.34g)", EXTREME_HOT_DAYS: "अत्यधिक गर्म दिन",
    FIRE_FREQUENCY: "आग की आवृत्ति", FIRE_INTENSITY: "आग की तीव्रता",
    HEATWAVE_DURATION: "लू की अवधि", HEATWAVE_FREQUENCY: "लू की आवृत्ति",
    HEATWAVE_SEVERITY: "लू की तीव्रता", LANDSLIDES_0P01: "भूस्खलन (0.01)",
    LANDSLIDES_0P1: "भूस्खलन (0.1)", MALARIA_FALCIPARUM: "मलेरिया (पी. फैल्सीपेरम)",
    MALARIA_VIVAX: "मलेरिया (पी. विवैक्स)", METEOROLOGICAL_DROUGHT_SPEI: "सूखा (SPEI)",
    METEOROLOGICAL_DROUGHT_SPI: "सूखा (SPI)", PM25: "वायु प्रदूषण (PM2.5)",
    RIVER_FLOOD: "नदी बाढ़", SDS_SUSCEPTIBILITY: "रेत और धूल भरी आँधी",
    VOLCANOES_100KM_BUFFER: "ज्वालामुखी (100 किमी)", WIND_SPEED: "अत्यधिक हवा",
  },
  bn: {
    AGRICULTURAL_STRESS: "কৃষি চাপ", COASTAL_FLOOD: "উপকূলীয় বন্যা",
    COMPLEX_EMERGENCIES_ACLED: "জটিল জরুরি অবস্থা", EARTHQUAKE_0P09: "ভূমিকম্প (0.09g)",
    EARTHQUAKE_0P34: "ভূমিকম্প (0.34g)", EXTREME_HOT_DAYS: "অতি উষ্ণ দিন",
    FIRE_FREQUENCY: "অগ্নিকাণ্ডের হার", FIRE_INTENSITY: "অগ্নিকাণ্ডের তীব্রতা",
    HEATWAVE_DURATION: "তাপপ্রবাহের স্থায়িত্ব", HEATWAVE_FREQUENCY: "তাপপ্রবাহের হার",
    HEATWAVE_SEVERITY: "তাপপ্রবাহের তীব্রতা", LANDSLIDES_0P01: "ভূমিধস (0.01)",
    LANDSLIDES_0P1: "ভূমিধস (0.1)", MALARIA_FALCIPARUM: "ম্যালেরিয়া (পি. ফ্যালসিপেরাম)",
    MALARIA_VIVAX: "ম্যালেরিয়া (পি. ভাইভ্যাক্স)", METEOROLOGICAL_DROUGHT_SPEI: "খরা (SPEI)",
    METEOROLOGICAL_DROUGHT_SPI: "খরা (SPI)", PM25: "বায়ুদূষণ (PM2.5)",
    RIVER_FLOOD: "নদীর বন্যা", SDS_SUSCEPTIBILITY: "বালু ও ধুলিঝড়",
    VOLCANOES_100KM_BUFFER: "আগ্নেয়গিরি (১০০ কিমি)", WIND_SPEED: "চরম বাতাস",
  },
};

export const indicatorLabel = (code: string, locale: Locale): string =>
  INDICATORS[locale]?.[code] ?? HAZARD_LABELS[code] ?? code;

/** The hazard-measure names ("Flood depth", "Peak ground acceleration") stay in
 *  English: they are technical descriptions of a source field, and the unit
 *  beside them comes from the database untranslated either way. */
export const measureLabel = (code: string, fallback: string): string =>
  HAZARD_MEASURE[code] ?? fallback;
