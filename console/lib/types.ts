export type Urgency = "same_day" | "today" | "this_week" | "check";
export type CaseStatus = "awaiting_approval" | "needs_evidence" | "notified";

export interface Check {
  name: string;
  passed: boolean;
  detail: string;
}

export interface Lot {
  lot_id: string;
  lot_code: string | null;
  lot_code_source: string | null;
  upc: string | null;
  brand: string | null;
  product_description: string;
  storage_location: string;
  donor: string | null;
  received_on: string | null;
  best_by: string | null;
  cases_on_hand: number;
  units_on_hand: number;
  units_per_case: number;
  units_distributed: number;
  label_photo: string | null;
  evidence_id: string;
  decided_by: string;
  outcome: string;
  missing: string[];
  checks: Check[];
}

export interface Recipient {
  household_id: string;
  name: string;
  household_size: number;
  children_under_5: number;
  units: number;
  last_given_on: string | null;
  language: string;
  lots: string[];
  contact_phone: string | null;
  contact_email: string | null;
}

export interface PullPlan {
  cases: number;
  units: number;
  locations: string[];
  lots: Lot[];
}

export interface NotifyPlan {
  households: number;
  units: number;
  children_under_5: number;
  recipients: Recipient[];
}

export interface Recall {
  recall_number: string;
  classification: string;
  class_i: boolean;
  recall_status: string;
  title: string;
  reason: string;
  firm: string;
  firm_location: string;
  distribution_pattern: string;
  quantity: string | null;
  recall_date: string | null;
  report_date: string | null;
  source: string;
}

export interface TimelineEvent {
  at: string;
  event: string;
  detail: string;
}

export interface Case {
  pantry_id: string;
  case_id: string;
  pantry_name: string;
  pantry_location: string;
  headline: string;
  urgency: Urgency;
  status: CaseStatus;
  recall: Recall;
  pull: PullPlan;
  notify: NotifyPlan;
  needs_evidence: Lot[];
  notice_text: string | null;
  delivery: unknown | null;
  evidence_uri: string | null;
  timeline: TimelineEvent[];
  created_at: string;
  updated_at: string;
}

export const URGENCY_ORDER: Record<Urgency, number> = {
  same_day: 0,
  today: 1,
  this_week: 2,
  check: 3,
};

export const URGENCY_WORD: Record<Urgency, string> = {
  same_day: "same day",
  today: "today",
  this_week: "this week",
  check: "go look",
};

export const LANGUAGE_NAME: Record<string, string> = {
  en: "English",
  es: "Spanish",
  ar: "Arabic",
  sw: "Swahili",
  vi: "Vietnamese",
  pl: "Polish",
  fr: "French",
  ru: "Russian",
  so: "Somali",
  ne: "Nepali",
  ps: "Pashto",
  fa: "Dari",
  am: "Amharic",
  ht: "Haitian Creole",
  zh: "Chinese",
};
