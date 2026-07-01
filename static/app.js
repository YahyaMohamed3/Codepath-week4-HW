"use strict";

// Small vanilla-JS client for the Provenance Guard demo. No frameworks, no CDN.

/** POST JSON and return {ok, status, data}. */
async function postJSON(url, body) {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  let data = null;
  try {
    data = await resp.json();
  } catch (_e) {
    data = { error: "invalid_response", message: "Non-JSON response." };
  }
  return { ok: resp.ok, status: resp.status, data };
}

function setStatus(el, message, kind) {
  el.textContent = message;
  el.className = "status" + (kind ? " " + kind : "");
}

function fmt(n) {
  return n === null || n === undefined ? "—" : Number(n).toFixed(3);
}

function attributionPill(attr) {
  const map = {
    likely_ai: "pill-ai",
    likely_human: "pill-human",
    uncertain: "pill-uncertain",
  };
  const cls = map[attr] || "pill-uncertain";
  return `<span class="attribution-pill ${cls}">${attr.replace("_", " ")}</span>`;
}

function signalRows(signals) {
  const rows = [];
  for (const [name, sig] of Object.entries(signals)) {
    const score = sig.available ? fmt(sig.score) : "unavailable";
    let extra = "";
    if (sig.reasoning) extra = sig.reasoning;
    else if (sig.matches && sig.matches.length)
      extra = "matched: " + sig.matches.slice(0, 5).join(", ");
    else if (sig.matched_tools && sig.matched_tools.length)
      extra = "tools: " + sig.matched_tools.join(", ");
    else if (sig.issues && sig.issues.length)
      extra = "issues: " + sig.issues.join(", ");
    else if (sig.metrics)
      extra = "CV " + fmt(sig.metrics.sentence_length_cv) +
              ", TTR " + fmt(sig.metrics.type_token_ratio);
    rows.push(
      `<tr><td>${name}</td><td>${score}</td><td>${extra || ""}</td></tr>`
    );
  }
  return rows.join("");
}

function renderResult(container, data) {
  const label = data.transparency_label || { variant: "uncertain", text: "" };
  const disagreement = data.signal_disagreement;
  let certBlock = "";
  if (data.certificate) {
    certBlock = `<div class="cert-badge"><strong>Verified Human Process.</strong>
      ${data.certificate.certificate_label || ""}</div>`;
  }
  container.innerHTML = `
    <div class="label-box ${label.variant}">
      <p style="margin:0 0 0.4rem">${attributionPill(data.attribution)}</p>
      <p style="margin:0">${label.text}</p>
    </div>
    <p><strong>Content ID:</strong> <code>${data.content_id}</code></p>
    <p><strong>AI likelihood:</strong> ${fmt(data.ai_likelihood)} &nbsp;
       <strong>Confidence:</strong> ${fmt(data.confidence)} &nbsp;
       <strong>Status:</strong> ${data.status}</p>
    <table class="scores">
      <thead><tr><th>Signal</th><th>Score</th><th>Detail</th></tr></thead>
      <tbody>${signalRows(data.signals || {})}</tbody>
    </table>
    <div class="disagreement-note">
      Signal disagreement: <strong>${fmt(disagreement)}</strong>.
      Higher disagreement lowers confidence — the system shows this instead of
      hiding it.
    </div>
    ${certBlock}`;
  container.hidden = false;
}

// --- Text submission ---
const submitForm = document.getElementById("submit-form");
if (submitForm) {
  submitForm.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const status = document.getElementById("submit-status");
    const result = document.getElementById("result");
    setStatus(status, "Analyzing…");
    const { ok, data } = await postJSON("/submit", {
      creator_id: document.getElementById("creator-id").value,
      text: document.getElementById("text").value,
    });
    if (!ok) {
      setStatus(status, data.message || "Submission failed.", "error");
      result.hidden = true;
      return;
    }
    setStatus(status, "Analysis complete.", "ok");
    renderResult(result, data);
    // Prefill appeal + certificate content IDs for convenience.
    document.getElementById("appeal-content-id").value = data.content_id;
    document.getElementById("cert-content-id").value = data.content_id;
  });
}

// --- Appeal ---
const appealForm = document.getElementById("appeal-form");
if (appealForm) {
  appealForm.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const status = document.getElementById("appeal-status");
    setStatus(status, "Submitting appeal…");
    const { ok, data } = await postJSON("/appeal", {
      content_id: document.getElementById("appeal-content-id").value,
      creator_id: document.getElementById("appeal-creator-id").value,
      creator_reasoning: document.getElementById("appeal-reasoning").value,
    });
    if (!ok) {
      setStatus(status, data.message || "Appeal failed.", "error");
      return;
    }
    setStatus(
      status,
      `${data.message} Status: ${data.status}. Appeal ID: ${data.appeal_id}`,
      "ok"
    );
  });
}

// --- Image metadata ---
const imageForm = document.getElementById("image-form");
if (imageForm) {
  imageForm.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const status = document.getElementById("image-status");
    const result = document.getElementById("image-result");
    let metadata;
    try {
      metadata = JSON.parse(document.getElementById("image-metadata").value);
    } catch (_e) {
      setStatus(status, "Metadata must be valid JSON.", "error");
      return;
    }
    setStatus(status, "Analyzing metadata…");
    const { ok, data } = await postJSON("/submit/image-metadata", {
      creator_id: document.getElementById("image-creator-id").value,
      metadata,
    });
    if (!ok) {
      setStatus(status, data.message || "Submission failed.", "error");
      result.hidden = true;
      return;
    }
    setStatus(status, "Analysis complete.", "ok");
    renderResult(result, data);
  });
}

// --- Certificate challenge + verify ---
let currentPhrase = null;
const challengeForm = document.getElementById("challenge-form");
if (challengeForm) {
  challengeForm.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const status = document.getElementById("challenge-status");
    const verifyForm = document.getElementById("verify-form");
    setStatus(status, "Requesting challenge…");
    const { ok, data } = await postJSON("/certificate/challenge", {
      content_id: document.getElementById("cert-content-id").value,
      creator_id: document.getElementById("cert-creator-id").value,
    });
    if (!ok) {
      setStatus(status, data.message || "Challenge failed.", "error");
      verifyForm.hidden = true;
      return;
    }
    currentPhrase = data.phrase;
    challengeForm.dataset.challengeId = data.challenge_id;
    setStatus(
      status,
      `Challenge phrase: "${data.phrase}". Include it in your process note. ` +
        `Expires ${data.expires_at}.`,
      "ok"
    );
    verifyForm.hidden = false;
  });
}

const verifyForm = document.getElementById("verify-form");
if (verifyForm) {
  verifyForm.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const status = document.getElementById("verify-status");
    const evidence = document
      .getElementById("verify-evidence")
      .value.split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    setStatus(status, "Verifying…");
    const { ok, data } = await postJSON("/certificate/verify", {
      challenge_id: challengeForm.dataset.challengeId,
      content_id: document.getElementById("cert-content-id").value,
      creator_id: document.getElementById("cert-creator-id").value,
      challenge_response: document.getElementById("verify-response").value,
      creator_attestation: document.getElementById("verify-attest").checked,
      draft_evidence: evidence,
    });
    if (!ok) {
      setStatus(status, data.message || "Verification failed.", "error");
      return;
    }
    setStatus(
      status,
      `Certificate issued (${data.certificate_id}). Status: ${data.status}.`,
      "ok"
    );
  });
}
