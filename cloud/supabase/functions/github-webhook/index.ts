// Supabase Edge Function: GitHub Webhook Receiver
// Verifies webhook signature, extracts event fields, and inserts into events table.

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const WEBHOOK_SECRET = Deno.env.get("GITHUB_WEBHOOK_SECRET");

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") {
    return new Response("Method not allowed", { status: 405 });
  }

  // Read body as text for signature verification
  const body = await req.text();

  // Verify webhook signature
  const signature = req.headers.get("x-hub-signature-256");
  if (!signature || !WEBHOOK_SECRET) {
    return new Response("Missing signature or secret", { status: 401 });
  }

  const isValid = await verifySignature(WEBHOOK_SECRET, signature, body);
  if (!isValid) {
    return new Response("Invalid signature", { status: 401 });
  }

  // Parse event
  const eventType = req.headers.get("x-github-event") || "unknown";
  const deliveryId = req.headers.get("x-github-delivery");
  const payload = JSON.parse(body);

  // Extract common fields
  const repo = payload.repository?.full_name || "unknown/unknown";
  const action = payload.action || "";
  const ref = extractRef(eventType, payload);
  const actor = payload.sender?.login || null;
  const summary = extractSummary(eventType, payload);

  // Insert into Supabase
  const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
  const supabaseKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
  const supabase = createClient(supabaseUrl, supabaseKey);

  const { error } = await supabase.from("events").insert({
    repo,
    event_type: eventType,
    action,
    ref,
    actor,
    summary,
    payload,
    delivery_id: deliveryId,
  });

  // Handle duplicate delivery_id gracefully (return 200)
  if (error) {
    if (error.code === "23505") {
      // Unique constraint violation — duplicate delivery
      return new Response(JSON.stringify({ status: "duplicate" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    console.error("Insert error:", error);
    return new Response(JSON.stringify({ error: error.message }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }

  return new Response(JSON.stringify({ status: "ok" }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
});

async function verifySignature(
  secret: string,
  signature: string,
  body: string
): Promise<boolean> {
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, encoder.encode(body));
  const computed = `sha256=${Array.from(new Uint8Array(sig))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")}`;
  return signature === computed;
}

function extractRef(eventType: string, payload: Record<string, any>): string | null {
  switch (eventType) {
    case "check_run":
      return payload.check_run?.check_suite?.head_branch || null;
    case "check_suite":
      return payload.check_suite?.head_branch || null;
    case "workflow_run":
      return payload.workflow_run?.head_branch || null;
    case "pull_request_review":
    case "pull_request_review_comment":
      return payload.pull_request?.head?.ref || null;
    default:
      return null;
  }
}

function extractSummary(eventType: string, payload: Record<string, any>): string {
  switch (eventType) {
    case "check_run":
      return `${payload.check_run?.name || "check"} ${payload.check_run?.conclusion || payload.action}`;
    case "check_suite":
      return `Check suite ${payload.check_suite?.conclusion || payload.action}`;
    case "workflow_run":
      return `${payload.workflow_run?.name || "workflow"} ${payload.workflow_run?.conclusion || payload.action}`;
    case "pull_request_review":
      return `Review ${payload.review?.state || payload.action} by ${payload.review?.user?.login || "unknown"}`;
    case "pull_request_review_comment":
      return `Comment by ${payload.comment?.user?.login || "unknown"}: ${(payload.comment?.body || "").slice(0, 100)}`;
    default:
      return `${eventType} ${payload.action || ""}`.trim();
  }
}
