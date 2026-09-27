/**
 * Saved replies for the ticket reply box. {first_name} becomes the person's first name
 * (the only part of their name the admin app shows); {number} the ticket's number.
 * Plain text: what staff send is shown to students as text, never as HTML.
 */
export interface SavedReply {
  id: string;
  label: string;
  body: string;
}

export const SAVED_REPLIES: SavedReply[] = [
  {
    id: "thanks-looking",
    label: "Thanks, we're looking into it",
    body: "Hi {first_name},\n\nThanks for letting us know. We're looking into this now and will write back here as soon as we know more.\n\nThe AnotherNote team",
  },
  {
    id: "need-details",
    label: "Can you tell us a bit more?",
    body: "Hi {first_name},\n\nThanks for getting in touch. So we can find what went wrong, could you tell us which browser and device you were using, and roughly what time it happened?\n\nPlease don't send passwords. If a part of your notes helps show the problem, you can paste just that part here.\n\nThe AnotherNote team",
  },
  {
    id: "fixed",
    label: "Fixed, please try again",
    body: "Hi {first_name},\n\nGood news: we've fixed this. Could you try again and let us know here if anything still looks wrong?\n\nThe AnotherNote team",
  },
  {
    id: "safari-audio",
    label: "Teach mode: no sound in Safari",
    body: "Hi {first_name},\n\nSafari keeps sound off until you've clicked on the page once. After the lesson starts, click anywhere on it and the voice should come in.\n\nThe AnotherNote team",
  },
  {
    id: "signed-out",
    label: "Signed out everywhere, as asked",
    body: "Hi {first_name},\n\nWe've signed your account out on every device, as you asked. It can take up to a minute everywhere. Sign in again with your password on the devices you use.\n\nThe AnotherNote team",
  },
  {
    id: "closing",
    label: "Closing this ticket",
    body: "Hi {first_name},\n\nWe haven't heard back for a while, so we're closing {number}. If it happens again, reply here and it will open again.\n\nThe AnotherNote team",
  },
];

export function fillReply(body: string, values: { first_name?: string | null; number?: string | null }): string {
  return body
    .replace(/\{first_name\}/g, values.first_name?.trim() || "there")
    .replace(/\{number\}/g, values.number?.trim() || "this ticket");
}
