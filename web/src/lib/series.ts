/**
 * What each chart series is, and its colour. Colour follows the thing, never its rank:
 * "Google" is slot 2 in every chart and every range, so filtering never repaints the
 * survivors. Slots are the validated palette in index.css (--viz-1 ... --viz-8), used in
 * order; anything unknown folds into "Other".
 *
 * The 19 metered features (spec 5.2.4) are too many for colour, so charts group them into
 * seven fixed areas; the per-feature detail is in the tables.
 */

export interface Series {
  key: string;
  label: string;
  color: string;
}

export const OTHER: Series = { key: "other", label: "Other", color: "var(--viz-other)" };

export const METHODS: Series[] = [
  { key: "password", label: "Password", color: "var(--viz-1)" },
  { key: "google", label: "Google", color: "var(--viz-2)" },
  { key: "microsoft", label: "Microsoft", color: "var(--viz-3)" },
  { key: "pin", label: "Child PIN", color: "var(--viz-4)" },
  { key: "desktop", label: "Desktop app", color: "var(--viz-5)" },
];

export const PROVIDERS: Series[] = [
  { key: "deepseek", label: "DeepSeek", color: "var(--viz-1)" },
  { key: "anthropic", label: "Anthropic", color: "var(--viz-2)" },
  { key: "perplexity", label: "Perplexity", color: "var(--viz-3)" },
  { key: "speechify", label: "Speechify", color: "var(--viz-4)" },
  { key: "whisper", label: "Whisper (local)", color: "var(--viz-5)" },
];

export interface FeatureArea extends Series {
  features: string[];
}

export const FEATURE_AREAS: FeatureArea[] = [
  { key: "teach", label: "Teach mode", color: "var(--viz-1)", features: ["teach.script", "teach.ask", "teach.facts", "teach.image_plan"] },
  { key: "voice", label: "Voice", color: "var(--viz-2)", features: ["tts"] },
  { key: "notes", label: "Notes", color: "var(--viz-3)", features: ["notes.generate", "notes.revise", "note_check"] },
  {
    key: "quizzes",
    label: "Quizzes and cards",
    color: "var(--viz-4)",
    features: ["quiz.hint", "quiz.section", "flashcards.section", "questions.more", "questions.generate"],
  },
  { key: "pictures", label: "Pictures", color: "var(--viz-5)", features: ["pictures.web_search", "pictures.check", "pictures.parts"] },
  { key: "sessions", label: "New sessions", color: "var(--viz-6)", features: ["session.create"] },
  { key: "transcription", label: "Transcription", color: "var(--viz-7)", features: ["transcribe.question", "transcribe.youtube"] },
];

const AREA_OF = new Map(FEATURE_AREAS.flatMap((area) => area.features.map((f) => [f, area] as const)));

export function areaOf(feature: string): Series {
  return AREA_OF.get(feature) ?? OTHER;
}

export const FEATURE_LABELS: Record<string, string> = {
  "teach.script": "Teach mode: lesson script",
  "teach.ask": "Teach mode: questions",
  "teach.facts": "Teach mode: key facts",
  "teach.image_plan": "Teach mode: picture plan",
  note_check: "Note checks",
  "pictures.web_search": "Pictures: web search",
  tts: "Voice (text to speech)",
  "transcribe.question": "Transcription: spoken questions",
  "pictures.check": "Pictures: checking",
  "pictures.parts": "Pictures: finding parts",
  "session.create": "New study session",
  "questions.more": "More questions",
  "notes.generate": "Notes: writing",
  "notes.revise": "Notes: revising",
  "quiz.hint": "Quiz hints",
  "quiz.section": "Section quizzes",
  "flashcards.section": "Section flashcards",
  "questions.generate": "Question generation",
  "transcribe.youtube": "Transcription: YouTube",
};

export function featureLabel(feature: string): string {
  return FEATURE_LABELS[feature] ?? feature;
}

export function seriesFor(list: Series[], key: string): Series {
  return list.find((s) => s.key === key) ?? { ...OTHER, key, label: key };
}

/** Status colour for things that went wrong (errors, failed sign-ins): always with a label. */
export const CRITICAL = "var(--viz-critical)";
export const ACCENT = "var(--viz-accent)";

export const REASONS: { id: string; label: string }[] = [
  { id: "sign_in", label: "Can't sign in, or locked" },
  { id: "upload", label: "Upload failed or won't open" },
  { id: "notes", label: "Notes, quiz or flashcards look wrong" },
  { id: "teach", label: "Teach mode: voice or mic" },
  { id: "pictures", label: "Board picture wrong or missing" },
  { id: "slow", label: "Slow, stuck or won't load" },
  { id: "family", label: "Family and child accounts" },
  { id: "study_tools", label: "Highlights, sticky notes, plans" },
  { id: "account", label: "Account, organisation or billing" },
  { id: "idea", label: "Idea or suggestion" },
  { id: "other", label: "Something else" },
];
