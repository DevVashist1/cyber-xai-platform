(() => {
  if (window.__cyberXaiGuardLoaded) return;
  window.__cyberXaiGuardLoaded = true;

  console.log("[+] Cyber XAI Insider Threat Guard active on:", window.location.hostname);

  let approvedOverrideText = "";
  let typingTimer = null;
  let lastAlertedSignature = "";

  function removeModal() {
    const existing = document.getElementById("cyber-xai-shadow-host");
    if (existing) existing.remove();
  }

  // ============================================================================
  // 1. VALIDATION CHECKSUMS (Luhn & Verhoeff)
  // ============================================================================
  function isValidLuhn(numStr) {
    const digits = numStr.replace(/\D/g, "");
    if (digits.length < 13 || digits.length > 19) return false;
    if (/^(\d)\1+$/.test(digits)) return false;
    let sum = 0;
    let shouldDouble = false;
    for (let i = digits.length - 1; i >= 0; i--) {
      let digit = parseInt(digits.charAt(i), 10);
      if (shouldDouble) {
        digit *= 2;
        if (digit > 9) digit -= 9;
      }
      sum += digit;
      shouldDouble = !shouldDouble;
    }
    return sum % 10 === 0;
  }

  const VERHOEFF_D = [
    [0,1,2,3,4,5,6,7,8,9],[1,2,3,4,0,6,7,8,9,5],[2,3,4,0,1,7,8,9,5,6],[3,4,0,1,2,8,9,5,6,7],[4,0,1,2,3,9,5,6,7,8],
    [5,9,8,7,6,0,4,3,2,1],[6,5,9,8,7,1,0,4,3,2],[7,6,5,9,8,2,1,0,4,3],[8,7,6,5,9,3,2,1,0,4],[9,8,7,6,5,4,3,2,1,0]
  ];
  const VERHOEFF_P = [
    [0,1,2,3,4,5,6,7,8,9],[1,5,7,6,2,8,3,0,9,4],[5,8,0,3,7,9,6,1,4,2],[8,9,1,6,0,4,3,5,2,7],
    [9,4,5,3,1,2,6,8,7,0],[4,2,8,6,5,7,3,9,0,1],[2,7,9,3,8,0,6,4,1,5],[7,0,4,6,9,1,3,2,5,8]
  ];
  function isValidVerhoeff(numStr) {
    const digits = numStr.replace(/\D/g, "");
    if (digits.length !== 12 || /^[01]/.test(digits)) return false;
    let c = 0;
    for (let i = 0; i < digits.length; i++) {
      const item = parseInt(digits.charAt(digits.length - 1 - i), 10);
      c = VERHOEFF_D[c][VERHOEFF_P[i % 8][item]];
    }
    return c === 0;
  }

  function computeShannonEntropy(str) {
    if (!str || str.length === 0) return 0;
    const freq = {};
    for (let i = 0; i < str.length; i++) {
      const ch = str[i];
      freq[ch] = (freq[ch] || 0) + 1;
    }
    let entropy = 0;
    const len = str.length;
    for (const ch in freq) {
      const p = freq[ch] / len;
      entropy -= p * Math.log2(p);
    }
    return entropy;
  }

  // ============================================================================
  // 2. 18-RULE REGEX CATALOGUE
  // ============================================================================
  function runRegexCatalogue(text) {
    const firedRules = [];
    let totalRegexHits = 0;

    if (/\bTEST-BLOCK-ME\b/i.test(text)) {
      firedRules.push({ id: "CM-01", category: "TEST_BLOCK_TRIGGER", weight: 1.0, hard: true });
      totalRegexHits += 1;
    }

    const id01Candidates = text.match(/\b[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}\b/g) || [];
    const validId01 = id01Candidates.filter(isValidVerhoeff);
    if (validId01.length > 0) {
      firedRules.push({ id: "ID-01", category: "NATIONAL_ID_VERHOEFF", weight: 0.8, hard: false });
      totalRegexHits += validId01.length;
    }

    const panMatches = text.match(/\b[A-Z]{3}[ABCFGHLJPTF][A-Z]\d{4}[A-Z]\b/g) || [];
    if (panMatches.length > 0) {
      firedRules.push({ id: "ID-02", category: "PAN_IDENTIFIER", weight: 0.7, hard: false });
      totalRegexHits += panMatches.length;
    }

    const ssnMatches = text.match(/\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b/g) || [];
    if (ssnMatches.length > 0) {
      firedRules.push({ id: "ID-03", category: "US_SSN", weight: 0.8, hard: false });
      totalRegexHits += ssnMatches.length;
    }

    const ccCandidates = text.match(/\b(?:\d[ -]*?){13,19}\b/g) || [];
    const validCards = ccCandidates.filter(isValidLuhn);
    if (validCards.length > 0) {
      firedRules.push({ id: "ID-04", category: "PAYMENT_CARD_LUHN", weight: 0.9, hard: true });
      totalRegexHits += validCards.length;
    }

    const emailMatches = text.match(/\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b/g) || [];
    if (emailMatches.length > 0) {
      const wt = emailMatches.length >= 5 ? Math.min(0.75, 0.5 + (emailMatches.length - 5) * 0.05) : 0.1;
      firedRules.push({ id: "ID-05", category: "EMAIL_PII", weight: wt, hard: false });
      totalRegexHits += emailMatches.length;
    }

    const phoneMatches = text.match(/(?:\+91[\-\s]?)?\b[6-9]\d{9}\b/g) || [];
    if (phoneMatches.length > 0) {
      const wt = phoneMatches.length >= 5 ? 0.5 : 0.1;
      firedRules.push({ id: "ID-06", category: "PHONE_NUMBER", weight: wt, hard: false });
      totalRegexHits += phoneMatches.length;
    }

    if (/\b[A-Z]{4}0[A-Z0-9]{6}\b/.test(text) && /\b(account|acct|bank|ifsc)\b/i.test(text)) {
      firedRules.push({ id: "ID-07", category: "BANK_IFSC_ACCOUNT", weight: 0.6, hard: false });
      totalRegexHits += 1;
    }

    if (/-----BEGIN (?:RSA |OPENSSH |EC |DSA |PGP |PRIVATE )?KEY-----/i.test(text)) {
      firedRules.push({ id: "SE-01", category: "PRIVATE_KEY", weight: 1.0, hard: true });
      totalRegexHits += 1;
    }

    if (/\b(?:AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|sk-[a-zA-Z0-9_-]{16,}|gh[pousr]_[a-zA-Z0-9]{20,}|AIza[0-9A-Za-z\-_]{35})\b/.test(text)) {
      firedRules.push({ id: "SE-02", category: "CLOUD_API_KEY", weight: 1.0, hard: true });
      totalRegexHits += 1;
    }

    const se03Match = text.match(/\b(?:key|token|secret|api_key|apikey|auth)\s*[:=]\s*["']?([A-Za-z0-9_\-+/=]{16,})["']?/i);
    if (se03Match) {
      const candidate = se03Match[1];
      const isUUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(candidate);
      const isGitHash = /^[0-9a-f]{40}$/i.test(candidate);
      if (!isUUID && !isGitHash && computeShannonEntropy(candidate) >= 3.6) {
        firedRules.push({ id: "SE-03", category: "HIGH_ENTROPY_SECRET", weight: 0.8, hard: false });
        totalRegexHits += 1;
      }
    }

    if (/\b(?:password|passwd|pwd)\s*[:=]\s*["']?(?!None\b|null\b|undefined\b|true\b|false\b|models\.|forms\.|char\b)[^\s"';,)]{4,}/i.test(text)) {
      firedRules.push({ id: "SE-04", category: "PASSWORD_ASSIGNMENT", weight: 0.9, hard: true });
      totalRegexHits += 1;
    }

    if (/\b(?:postgres|postgresql|mysql|mongodb(?:\+srv)?|redis|amqp|mssql):\/\/[^:\s]+:[^@\s]+@[^\s]+/i.test(text)) {
      firedRules.push({ id: "SE-05", category: "DB_CONNECTION_STRING", weight: 1.0, hard: true });
      totalRegexHits += 1;
    }

    if (/\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}\b/.test(text)) {
      firedRules.push({ id: "SE-06", category: "JWT_TOKEN", weight: 0.8, hard: false });
      totalRegexHits += 1;
    }

    if (/\bAuthorization\s*:\s*Bearer\s+[A-Za-z0-9_\-\.~+/]+=*/i.test(text)) {
      firedRules.push({ id: "SE-07", category: "BEARER_TOKEN", weight: 0.7, hard: false });
      totalRegexHits += 1;
    }

    const lines = text.split(/\r\n|\r|\n/);
    const codeKeywordHits = (text.match(/\b(def|function|class|import|from|return|const|let|var|if|else|for|while|try|catch|async|await|public|private|void)\b/g) || []).length;
    if (lines.length >= 30 && codeKeywordHits >= 8) {
      firedRules.push({ id: "CO-01", category: "LARGE_CODE_BLOCK", weight: 0.25, hard: false });
      totalRegexHits += 1;
    }

    if (/\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}|[\w-]+\.(?:internal|corp|lan|intranet))\b/i.test(text)) {
      firedRules.push({ id: "CO-02", category: "INTERNAL_INFRA_IP_HOST", weight: 0.5, hard: false });
      totalRegexHits += 1;
    }

    if (/\b(?:git@|https?:\/\/(?:gitlab|github|bitbucket)\.internal)\b/i.test(text)) {
      firedRules.push({ id: "CO-03", category: "INTERNAL_REPO_PATH", weight: 0.5, hard: false });
      totalRegexHits += 1;
    }

    if (/\b(?:SELECT\s+\*\s+FROM|INSERT\s+INTO|DELETE\s+FROM|DROP\s+TABLE)\b[\s\S]{1,80}\b(?:user_daily_activity|ext_paste_event|ext_device|beh_daily_score|users)\b/i.test(text)) {
      firedRules.push({ id: "CO-04", category: "INTERNAL_SQL_QUERY", weight: 0.5, hard: false });
      totalRegexHits += 1;
    }

    const hasConfMarker = /\b(?:confidential|internal\s+only|internal\s+use\s+only|do\s+not\s+distribute|not\s+for\s+external|top\s+secret)\b/i.test(text);
    if (hasConfMarker) {
      firedRules.push({ id: "CM-01", category: "CONFIDENTIALITY_MARKER", weight: 0.7, hard: false });
      totalRegexHits += 1;
    }

    if (/\b(?:PROJECT[-_\s]?OMEGA|PROJECT[-_\s]?TITAN|OPERATION[-_\s]?NIGHTFALL)\b/i.test(text)) {
      firedRules.push({ id: "CM-02", category: "PROJECT_CODENAME", weight: 0.6, hard: false });
      totalRegexHits += 1;
    }

    const certIds = new Set(text.match(/\b[A-Z]{3}\d{4}\b/g) || []);
    if (certIds.size >= 3) {
      firedRules.push({ id: "CM-03", category: "BULK_EMPLOYEE_IDS", weight: 0.5, hard: false });
      totalRegexHits += certIds.size;
    }

    let prodComplement = 1.0;
    let maxRuleWeight = 0.0;
    let hardFired = false;
    for (const r of firedRules) {
      prodComplement *= (1.0 - r.weight);
      if (r.weight > maxRuleWeight) maxRuleWeight = r.weight;
      if (r.hard) hardFired = true;
    }
    const regexScore = Number((1.0 - prodComplement).toFixed(4));

    return {
      firedRules,
      regexScore,
      maxRuleWeight,
      hardFired,
      totalRegexHits,
      emailAndPhoneCount: emailMatches.length + phoneMatches.length,
      hasConfMarker: hasConfMarker ? 1 : 0,
      lines,
      codeKeywordHits
    };
  }

  // ============================================================================
  // 3. 18-FEATURE LOGISTIC REGRESSION SCORER
  // ============================================================================
  const DEFAULT_LR_MODEL = {
    bias: -2.45,
    weights: [0.15, 0.12, 0.30, 0.10, 0.18, -0.10, 0.35, 0.45, 0.10, 0.10, 0.10, 0.35, 0.25, 0.65, 0.95, 0.50, 0.45, 0.70],
    mean: [4.5, 1.5, 0.05, 0.08, 0.05, 0.15, 3.8, 3.2, 45.0, 0.02, 0.01, 0.1, 0.05, 0.2, 0.1, 0.2, 0.2, 0.02],
    std:  [1.8, 1.2, 0.10, 0.08, 0.06, 0.08, 0.8, 1.2, 35.0, 0.04, 0.03, 0.3, 0.12, 0.6, 0.3, 0.6, 1.0, 0.15]
  };

  function evaluatePasteText(text) {
    const cat = runRegexCatalogue(text);
    const len = Math.max(1, text.length);
    const lines = cat.lines;
    const lineCount = Math.max(1, lines.length);

    const digits = (text.match(/\d/g) || []).length;
    const uppers = (text.match(/[A-Z]/g) || []).length;
    const whites = (text.match(/\s/g) || []).length;
    const puncts = (text.match(/[^\w\s]/g) || []).length;

    const tokens = text.trim().split(/\s+/).filter(Boolean);
    const tokenCount = Math.max(1, tokens.length);
    const longTokens = tokens.filter((t) => t.length >= 20);
    const maxTokenEntropy = longTokens.length > 0 ? Math.max(...longTokens.map(computeShannonEntropy)) : 0.0;
    const codeSymbols = (text.match(/[{}();[\]=<>]/g) || []).length;
    const numericTokens = tokens.filter((t) => /^\d+(?:\.\d+)?$/.test(t)).length;
    const distinctCategories = new Set(cat.firedRules.map((r) => r.id.split("-")[0])).size;

    const rawFeatures = [
      Math.log1p(len), Math.log1p(lineCount), digits / len, uppers / len,
      puncts / len, whites / len, computeShannonEntropy(text), maxTokenEntropy,
      len / lineCount, codeSymbols / len, cat.codeKeywordHits / tokenCount, 0.0,
      numericTokens / tokenCount, Math.log1p(cat.totalRegexHits), cat.maxRuleWeight,
      distinctCategories, cat.emailAndPhoneCount, cat.hasConfMarker
    ];

    let z = DEFAULT_LR_MODEL.bias;
    for (let i = 0; i < 18; i++) {
      const stdVal = (rawFeatures[i] - DEFAULT_LR_MODEL.mean[i]) / (DEFAULT_LR_MODEL.std[i] || 1);
      z += stdVal * DEFAULT_LR_MODEL.weights[i];
    }
    const mlScore = Number((1 / (1 + Math.exp(-z))).toFixed(4));

    let finalScore = 0.6 * cat.regexScore + 0.4 * mlScore;
    if (cat.hardFired && finalScore < 0.90) finalScore = 0.90;
    finalScore = Number(Math.min(1.0, finalScore).toFixed(4));

    let riskTier = "low";
    let action = "logged";
    if (finalScore >= 0.70) {
      riskTier = "high";
      action = "blocked";
    } else if (finalScore >= 0.35) {
      riskTier = "medium";
      action = "warned";
    }

    return {
      regexScore: Number(cat.regexScore.toFixed(3)),
      mlScore: Number(mlScore.toFixed(3)),
      finalScore: Number(finalScore.toFixed(3)),
      riskTier,
      action,
      matchedCategories: cat.firedRules.map((r) => `${r.id}:${r.category}`),
      lineCount
    };
  }

  // ============================================================================
  // 4. FIND EDITOR & OVERRIDE INSERTION
  // ============================================================================
  function findActiveEditor(node) {
    if (node && (node.tagName === "TEXTAREA" || node.tagName === "INPUT")) return node;
    if (node && node.closest) {
      const el = node.closest('.ql-editor, #prompt-textarea, [contenteditable="true"], [role="textbox"], textarea, input');
      if (el) return el;
    }
    return document.querySelector('.ql-editor, #prompt-textarea, [contenteditable="true"], [role="textbox"], textarea');
  }

  function getEditorText(el) {
    if (!el) return "";
    if (typeof el.value === "string") return el.value;
    return el.innerText || el.textContent || "";
  }

  function insertApprovedText(targetNode, text) {
    approvedOverrideText = text.trim();
    const box = findActiveEditor(targetNode);
    if (!box) return;

    box.focus();

    if (typeof box.value === "string") {
      box.value = (box.value ? box.value + "\n" : "") + text;
      box.dispatchEvent(new Event("input", { bubbles: true }));
      return;
    }

    if ((box.innerText || "").includes(text.trim())) return;

    try {
      const sel = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(box);
      range.collapse(false);
      sel.removeAllRanges();
      sel.addRange(range);
      if (document.execCommand("insertText", false, text)) {
        box.dispatchEvent(new Event("input", { bubbles: true }));
        return;
      }
    } catch (_) {}

    if (box.classList && box.classList.contains("ql-blank")) {
      box.innerHTML = "";
      box.classList.remove("ql-blank");
    }
    const p = document.createElement("p");
    p.innerText = text;
    box.appendChild(p);
    box.dispatchEvent(new Event("input", { bubbles: true }));
  }

  // ============================================================================
  // 5. SHADOW DOM MODAL (Runs even if extension is toggled OFF in chrome://extensions)
  // ============================================================================
  function showShadowModal(evalResult, editableEl, rawText, onOverride) {
    removeModal();

    const host = document.createElement("div");
    host.id = "cyber-xai-shadow-host";
    host.style.cssText = "position: fixed !important; top: 20px !important; right: 20px !important; z-index: 2147483647 !important; display: block !important;";
    const shadow = host.attachShadow({ mode: "open" });

    const isBlocked = evalResult.action === "blocked";
    const accent = isBlocked ? "#dc2626" : "#d97706";
    const title = isBlocked ? "🛑 HIGH RISK — ACTION BLOCKED" : "⚠️ MEDIUM RISK — SENSITIVE DATA WARNING";
    const cats = evalResult.matchedCategories.length > 0 ? evalResult.matchedCategories.join(", ") : "Sensitive Pattern";

    shadow.innerHTML = `
      <style>
        .card { width: 385px; background: #111827; color: #f9fafb; border-radius: 10px; border: 2px solid ${accent}; box-shadow: 0 20px 40px rgba(0,0,0,0.65); font-family: system-ui, -apple-system, Arial, sans-serif; overflow: hidden; }
        .header { background: ${accent}; color: #fff; padding: 11px 15px; font-weight: 700; font-size: 13px; display: flex; justify-content: space-between; align-items: center; }
        .body { padding: 14px 15px; font-size: 12px; line-height: 1.45; }
        .meta { background: #1f2937; border: 1px solid #374151; padding: 9px; border-radius: 6px; margin: 10px 0; font-size: 11px; word-break: break-word; }
        .override-box { margin-top: 10px; display: none; }
        .override-box input { width: 100%; box-sizing: border-box; padding: 8px; border-radius: 5px; border: 1px solid #4b5563; background: #1f2937; color: #fff; font-size: 12px; margin-bottom: 8px; }
        .actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 10px; }
        button { border: none; padding: 7px 12px; border-radius: 5px; cursor: pointer; font-weight: 600; font-size: 11px; }
        .btn-override { background: #2563eb; color: #fff; }
        .btn-dismiss { background: #374151; color: #f3f4f6; }
        .btn-confirm { background: #16a34a; color: #fff; width: 100%; padding: 8px; }
      </style>
      <div class="card">
        <div class="header">
          <span>🛡️ Cyber XAI Insider Threat Guard</span>
          <span>${evalResult.riskTier.toUpperCase()}</span>
        </div>
        <div class="body">
          <div style="font-weight: 700; font-size: 13px; margin-bottom: 4px;">${title}</div>
          <div style="color: #d1d5db;">
            ${isBlocked
              ? "This action was blocked because sensitive or policy-violating patterns were detected locally."
              : "Potentially sensitive patterns were detected. Metadata has been logged."}
          </div>
          <div class="meta">
            <div><strong>Rule Categories:</strong> <span style="color:#fca5a5;">${cats}</span></div>
            <div><strong>Final Score:</strong> ${evalResult.finalScore} (Regex: ${evalResult.regexScore} | ML: ${evalResult.mlScore})</div>
          </div>
          ${isBlocked ? `
            <div class="override-box" id="overrideBox">
              <input type="text" id="overrideReasonInput" placeholder="Enter required reason (e.g., testing)..." />
              <button class="btn-confirm" id="confirmOverrideBtn">Submit Override & Insert Text</button>
            </div>
          ` : ""}
          <div class="actions">
            ${isBlocked ? `<button class="btn-override" id="showOverrideBtn">I need to proceed</button>` : ""}
            <button class="btn-dismiss" id="dismissBtn">Dismiss</button>
          </div>
        </div>
      </div>
    `;

    (document.body || document.documentElement).appendChild(host);

    shadow.getElementById("dismissBtn").addEventListener("click", () => host.remove());

    if (isBlocked) {
      const showBtn = shadow.getElementById("showOverrideBtn");
      const box = shadow.getElementById("overrideBox");
      const input = shadow.getElementById("overrideReasonInput");
      const confirmBtn = shadow.getElementById("confirmOverrideBtn");

      showBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        box.style.display = "block";
        showBtn.style.display = "none";
        input.focus();
      });

      const doConfirm = () => {
        const reason = input.value.trim();
        if (reason.length < 2) {
          input.style.borderColor = "#dc2626";
          input.placeholder = "Reason required (min 2 chars)!";
          return;
        }
        host.remove();
        if (rawText) insertApprovedText(editableEl, rawText);
        if (onOverride) onOverride(reason);
      };

      confirmBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        doConfirm();
      });

      input.addEventListener("keydown", (e) => {
        e.stopPropagation();
        if (e.key === "Enter") {
          e.preventDefault();
          doConfirm();
        }
      });
    }
  }

  // ============================================================================
  // 6. SAFE METADATA DISPATCH (Silent fallback if extension background is off)
  // ============================================================================
  function sendMetadata(eventType, contentLength, lineCount, fileExtension, evalResult, overrideUsed, overrideReason) {
    try {
      if (typeof chrome === "undefined" || !chrome.runtime || !chrome.runtime.id) return;
      chrome.storage.local.get(["rulesetVersion", "modelVersion"], (cfg) => {
        if (chrome.runtime.lastError) return;
        const safeCfg = cfg || {};
        const payload = {
          event_id: crypto.randomUUID(),
          occurred_at: new Date().toISOString(),
          site_domain: window.location.hostname || "local.test",
          event_type: eventType,
          content_length: contentLength,
          line_count: lineCount,
          file_extension: fileExtension,
          matched_categories: evalResult.matchedCategories,
          regex_score: evalResult.regexScore,
          ml_score: evalResult.mlScore,
          final_score: evalResult.finalScore,
          risk_tier: evalResult.riskTier,
          action: evalResult.action,
          override_used: Boolean(overrideUsed),
          override_reason: overrideReason || null,
          ruleset_version: safeCfg.rulesetVersion || 1,
          model_version: safeCfg.modelVersion || 1
        };
        try {
          chrome.runtime.sendMessage({ type: "LOG_DLP_EVENT", payload }, () => {
            void chrome.runtime.lastError;
          });
        } catch (_) {}
      });
    } catch (_) {}
  }

  // ============================================================================
  // 7. PERSISTENT LISTENERS (Stay active in open tabs even when toggled OFF)
  // ============================================================================
  document.addEventListener("paste", (event) => {
    if (event.target && event.target.id === "cyber-xai-shadow-host") return;

    const pastedText = (event.clipboardData || window.clipboardData)?.getData("text/plain") || "";
    if (!pastedText) return;

    if (approvedOverrideText && pastedText.trim() === approvedOverrideText) return;

    const evalResult = evaluatePasteText(pastedText);
    const editableEl = findActiveEditor(event.target);

    if (evalResult.action === "blocked") {
      event.preventDefault();
      event.stopPropagation();
      showShadowModal(evalResult, editableEl, pastedText, (reason) => {
        sendMetadata("paste", pastedText.length, evalResult.lineCount, null, evalResult, true, reason);
      });
    } else if (evalResult.action === "warned") {
      showShadowModal(evalResult, editableEl, pastedText, null);
    }

    sendMetadata("paste", pastedText.length, evalResult.lineCount, null, evalResult, false, null);
  }, true);

  document.addEventListener("input", (event) => {
    if (event.target && event.target.id === "cyber-xai-shadow-host") return;

    const editableEl = findActiveEditor(event.target);
    if (!editableEl) return;

    clearTimeout(typingTimer);
    typingTimer = setTimeout(() => {
      const currentText = getEditorText(editableEl).trim();
      if (!currentText || currentText.length < 6) return;
      if (currentText === approvedOverrideText) return;

      const evalResult = evaluatePasteText(currentText);
      const sig = `${evalResult.action}:${evalResult.matchedCategories.join(",")}:${currentText.length}`;

      if ((evalResult.action === "blocked" || evalResult.action === "warned") && sig !== lastAlertedSignature) {
        lastAlertedSignature = sig;
        showShadowModal(evalResult, editableEl, currentText, (reason) => {
          sendMetadata("paste", currentText.length, evalResult.lineCount, null, evalResult, true, reason);
        });
        sendMetadata("paste", currentText.length, evalResult.lineCount, null, evalResult, false, null);
      }
    }, 350);
  }, true);

  function checkUploadedFiles(files, event) {
    if (!files || files.length === 0) return;
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const parts = (file.name || "").split(".");
      const ext = parts.length > 1 ? parts.pop().toLowerCase().slice(0, 16) : "none";
      const sizeBytes = file.size || 0;

      const highExts = ["pem", "key", "env", "sql", "pfx", "p12", "kdbx", "ovpn", "id_rsa"];
      const medExts = ["csv", "parquet", "xlsx", "xls", "json", "db", "sqlite", "dump", "bak", "zip"];

      let regexScore = 0.1;
      let mlScore = sizeBytes > 1048576 ? 0.6 : 0.2;
      const matchedCategories = [];

      if (highExts.includes(ext)) {
        regexScore = 0.95;
        matchedCategories.push(`UPLOAD_SENSITIVE_EXT:${ext}`);
      } else if (medExts.includes(ext)) {
        regexScore = 0.55;
        matchedCategories.push(`UPLOAD_DATA_EXT:${ext}`);
      }

      const finalScore = Number((0.6 * regexScore + 0.4 * mlScore).toFixed(3));
      const riskTier = finalScore >= 0.70 ? "high" : (finalScore >= 0.35 ? "medium" : "low");
      const action = riskTier === "high" ? "blocked" : (riskTier === "medium" ? "warned" : "logged");
      const evalResult = { regexScore, mlScore, finalScore, riskTier, action, matchedCategories, lineCount: 0 };

      if (action === "blocked") {
        event.preventDefault();
        event.stopPropagation();
        if (event.target && event.target.tagName === "INPUT") event.target.value = "";
        showShadowModal(evalResult, null, "", (reason) => {
          sendMetadata("upload", sizeBytes, 0, ext, evalResult, true, reason);
        });
      } else if (action === "warned") {
        showShadowModal(evalResult, null, "", null);
      }
      sendMetadata("upload", sizeBytes, 0, ext, evalResult, false, null);
    }
  }

  document.addEventListener("change", (e) => {
    if (e.target && e.target.tagName === "INPUT" && e.target.type === "file") {
      checkUploadedFiles(e.target.files, e);
    }
  }, true);

  document.addEventListener("drop", (e) => {
    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      checkUploadedFiles(e.dataTransfer.files, e);
    }
  }, true);
})();