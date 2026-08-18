/* Peptide Evidence — answer-first client.
   All corpus and model text is written through textContent or createTextNode;
   this file never assigns raw markup. User questions are never logged. */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const PUBMED = "https://pubmed.ncbi.nlm.nih.gov/";
  const CITATION_MARKER = /\[(\d+)\]/g;
  const SNIPPET_MARKER = /\[\[([^\]]+)\]\]/g;
  const MAX_QUESTION = 500;

  const PEPTIDE_MENTIONS = Object.freeze([
    { pattern: /\bbpc[-\s]?157\b|body protection compound/i, label: "BPC-157" },
    { pattern: /\bghk(?:-cu)?\b/i, label: "GHK-Cu" },
    { pattern: /\btb[-\s]?500\b|\bthymosin\s+(?:beta|β)[-\s]?4\b/i, label: "TB-500 / thymosin beta-4" },
    { pattern: /\bipamorelin\b/i, label: "ipamorelin" },
    { pattern: /\btesamorelin\b/i, label: "tesamorelin" },
    { pattern: /\bepit(?:al|hal)on\b/i, label: "Epitalon" },
    { pattern: /\bmots[-\s]?c\b/i, label: "MOTS-c" },
    { pattern: /\bpt[-\s]?141\b|\bbremelanotide\b/i, label: "PT-141 / bremelanotide" },
  ]);

  const REFUSALS = Object.freeze({
    medical_safety: { label: "Medical-safety boundary", tone: "boundary", icon: "shield" },
    insufficient_evidence: { label: "Insufficient evidence", tone: "boundary", icon: "search" },
    service_unavailable: { label: "Service unavailable", tone: "system", icon: "warning" },
    budget_limit: { label: "Daily budget reached", tone: "system", icon: "clock" },
  });

  const ICON_PATHS = Object.freeze({
    shield: ["M12 3l7.5 3.2v5c0 4.4-3.1 8.3-7.5 9.6-4.4-1.3-7.5-5.2-7.5-9.6v-5z"],
    search: ["M11 4a7 7 0 100 14 7 7 0 000-14z", "M16.2 16.2L21 21"],
    warning: ["M12 4l9 16H3z", "M12 10v4", "M12 17.5v.01"],
    clock: ["M12 3.5a8.5 8.5 0 100 17 8.5 8.5 0 000-17z", "M12 7.5V12l3 2"],
    arrow: ["M5 12h13", "M12 5l7 7-7 7"],
    swap: ["M8 6l-4 6 4 6", "M16 6l4 6-4 6"],
  });

  // semanticAvailable stays null until /api/metrics answers; only an explicit
  // false is used to explain an empty hybrid or semantic result.
  let state = { question: "", sources: [], answerText: "", pending: false, semanticAvailable: null };

  /* ---------- small DOM helpers ---------- */

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = String(text);
    return node;
  }

  function icon(name, className) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    svg.setAttribute("class", className ? "icon " + className : "icon");
    (ICON_PATHS[name] || []).forEach((d) => {
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", d);
      svg.append(path);
    });
    return svg;
  }

  function externalLink(href, className, text) {
    const link = el("a", className, text);
    link.href = href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    return link;
  }

  function clear(node) { if (node) node.replaceChildren(); }

  const prefersReducedMotion = () =>
    typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function bringIntoView(node, block) {
    if (!node) return;
    node.scrollIntoView({ block: block || "start", behavior: prefersReducedMotion() ? "auto" : "smooth" });
  }

  function setStatus(message, isError) {
    const node = $("status");
    node.textContent = message == null ? "" : String(message);
    node.className = isError ? "status is-error" : "status";
  }

  /* ---------- reading the form ---------- */

  const intent = () => (document.querySelector('input[name="intent"]:checked') || {}).value || "answer";
  const answerMode = () => (document.querySelector('input[name="answer-mode"]:checked') || {}).value || "hybrid";
  const literatureMode = () => (document.querySelector('input[name="literature-mode"]:checked') || {}).value || "hybrid";
  const recordCount = () => Number($("records").value) || 5;

  const MODE_LABELS = Object.freeze({
    hybrid: "Hybrid", semantic: "Semantic", lexical: "Keyword", bm25: "BM25", boolean: "Boolean",
  });

  function refreshSummary() {
    const literature = intent() === "literature";
    const mode = literature ? literatureMode() : answerMode();
    const parts = [literature ? "Literature results" : "Evidence answer", MODE_LABELS[mode] || mode];
    if (!literature) parts.push(recordCount() + " records");
    $("advanced-summary").textContent = parts.join(" · ");
    $("answer-modes").hidden = literature;
    $("literature-modes").hidden = !literature;
    $("records-field").hidden = literature;
    $("ask-button-label").textContent = literature ? "Search the literature" : "Ask Peptide Evidence";
  }

  function refreshCounter() {
    const length = $("question").value.length;
    const counter = $("question-counter");
    counter.textContent = length + " / " + MAX_QUESTION;
    counter.className = length > MAX_QUESTION - 40 ? "counter is-near" : "counter";
  }

  /* ---------- rendering: answer text with citation markers ---------- */

  function citationIndex(citations) {
    const map = new Map();
    (citations || []).forEach((citation) => {
      if (!citation || typeof citation !== "object") return;
      const id = Number(citation.citation_id);
      if (!Number.isInteger(id)) return;
      map.set(id, citation);
    });
    return map;
  }

  function renderAnswerText(container, text, citations) {
    const map = citationIndex(citations);
    String(text || "").split(/\n{2,}/).forEach((block) => {
      if (!block.trim()) return;
      const paragraph = el("p", "answer-text");
      let cursor = 0;
      CITATION_MARKER.lastIndex = 0;
      let match = CITATION_MARKER.exec(block);
      while (match) {
        paragraph.append(document.createTextNode(block.slice(cursor, match.index)));
        const id = Number(match[1]);
        const citation = map.get(id);
        if (citation && citation.pubmed_url) {
          const link = externalLink(citation.pubmed_url, "cite", String(id));
          link.setAttribute("aria-label", "Citation " + id + ": " + (citation.title || "PubMed record " + citation.pmid));
          paragraph.append(link);
        } else {
          paragraph.append(el("span", "cite", String(id)));
        }
        cursor = match.index + match[0].length;
        match = CITATION_MARKER.exec(block);
      }
      paragraph.append(document.createTextNode(block.slice(cursor)));
      container.append(paragraph);
    });
    if (!container.childNodes.length) container.append(el("p", "answer-text", String(text || "")));
  }

  /* One abstract can supply two chunks, so the model may cite the same PMID
     under two ids. Show one card per record and list every marker on it. */
  function groupCitations(citations) {
    const order = [];
    const byPmid = new Map();
    citations.forEach((citation) => {
      if (!citation || typeof citation !== "object") return;
      const pmid = String(citation.pmid || "");
      const key = pmid || "citation-" + citation.citation_id;
      if (!byPmid.has(key)) {
        byPmid.set(key, {
          numbers: [],
          title: citation.title || ("PubMed record " + pmid),
          pmid: pmid,
          url: citation.pubmed_url || (pmid ? PUBMED + pmid + "/" : ""),
        });
        order.push(key);
      }
      byPmid.get(key).numbers.push(citation.citation_id);
    });
    return order.map((key) => {
      const entry = byPmid.get(key);
      return { n: entry.numbers.join(", "), title: entry.title, pmid: entry.pmid, url: entry.url };
    });
  }

  function groupRetrievedSources(items) {
    const order = [];
    const byRecord = new Map();
    items.forEach((item, index) => {
      if (!item || typeof item !== "object") return;
      const pmid = String(item.pmid || "");
      const key = pmid || "result-" + index;
      if (!byRecord.has(key)) {
        byRecord.set(key, {
          numbers: [],
          title: item.title || (pmid ? "PubMed record " + pmid : "Untitled record"),
          pmid: pmid,
          url: item.pubmed_url || (pmid ? PUBMED + pmid + "/" : ""),
        });
        order.push(key);
      }
      const rank = Number.isInteger(item.rank) && item.rank > 0 ? item.rank : index + 1;
      byRecord.get(key).numbers.push(rank);
    });
    return order.map((key) => {
      const entry = byRecord.get(key);
      return { n: entry.numbers.join(", "), title: entry.title, pmid: entry.pmid, url: entry.url };
    });
  }

  function evidenceScope(items) {
    const passages = items.length;
    const pmids = new Set(items.map((item) => String((item && item.pmid) || "")).filter(Boolean));
    const records = pmids.size || passages;
    const containsChunks = items.some((item) => item && item.chunk_id);
    if (containsChunks) {
      return { passages, records, label: passages + " retrieved passage" + (passages === 1 ? "" : "s") +
        " from " + records + " PubMed record" + (records === 1 ? "" : "s") };
    }
    return { passages, records, label: records + " PubMed record" + (records === 1 ? "" : "s") + " retrieved" };
  }

  function renderSnippet(node, value) {
    const source = value == null ? "" : String(value);
    let cursor = 0;
    SNIPPET_MARKER.lastIndex = 0;
    let match = SNIPPET_MARKER.exec(source);
    while (match) {
      node.append(document.createTextNode(source.slice(cursor, match.index)));
      node.append(el("mark", null, match[1]));
      cursor = match.index + match[0].length;
      match = SNIPPET_MARKER.exec(source);
    }
    node.append(document.createTextNode(source.slice(cursor)));
  }

  /* ---------- rendering: sources and evidence ---------- */

  function sourceCard(source) {
    const card = el("article", "source-card");
    card.append(el("span", "source-number", source.n));
    const body = el("div", "source-body");
    if (source.url) {
      body.append(externalLink(source.url, "source-title", source.title));
      body.append(externalLink(source.url, "source-pmid", "PMID " + source.pmid));
    } else {
      body.append(el("span", "source-title", source.title));
    }
    card.append(body);
    return card;
  }

  function renderSources(sources, heading) {
    $("sources-heading").textContent = heading;
    $("sources-count").textContent = sources.length + (sources.length === 1 ? " record" : " records");
    const list = $("sources-list");
    clear(list);
    if (!sources.length) {
      list.append(el("p", "callout callout-quiet", "No records were retrieved for this question."));
      return;
    }
    sources.forEach((source) => list.append(sourceCard(source)));
  }

  function evidenceRecord(item, position) {
    const record = el("article", "evidence-record");
    record.append(el("span", "source-number", Number.isInteger(item.rank) && item.rank > 0 ? item.rank : position));
    const body = el("div", "source-body");
    const url = item.pubmed_url || (item.pmid ? PUBMED + item.pmid + "/" : "");
    body.append(url ? externalLink(url, "source-title", item.title) : el("span", "source-title", item.title));

    const excerpt = el("p", "evidence-excerpt");
    renderSnippet(excerpt, item.snippet);
    body.append(excerpt);

    const meta = el("div", "evidence-meta");
    if (url) meta.append(externalLink(url, "tag tag-link", "PMID " + item.pmid));
    if (item.chunk_id) meta.append(el("span", "tag", String(item.chunk_id)));
    if (Number.isFinite(item.start_char) && Number.isFinite(item.end_char)) {
      meta.append(el("span", "tag", "chars " + item.start_char + "–" + item.end_char));
    }
    const ranks = [];
    if (Number.isFinite(item.lexical_rank)) ranks.push("Lexical #" + item.lexical_rank);
    if (Number.isFinite(item.semantic_rank)) ranks.push("Semantic #" + item.semantic_rank);
    if (ranks.length) meta.append(el("span", "tag", ranks.join(" · ")));
    else if (item.mode) meta.append(el("span", "tag", String(item.mode)));
    if (typeof item.score === "number" && Number.isFinite(item.score)) {
      meta.append(el("span", "tag", "score " + item.score.toFixed(3)));
    }
    body.append(meta);
    record.append(body);
    return record;
  }

  function renderEvidence(items) {
    const body = $("evidence-body");
    clear(body);
    if (!items.length) {
      body.append(el("p", "evidence-note", "No supporting records were returned."));
      return;
    }
    items.forEach((item, index) => body.append(evidenceRecord(item, index + 1)));
    body.append(el("p", "evidence-note",
      "A score is a ranking artifact, not a measure of study quality. Evidence comes from abstracts only."));
  }

  /* ---------- rendering: refusals and fallback ---------- */

  function renderRefusal(container, data) {
    const reason = REFUSALS[data.refusal_reason];
    const wrapper = el("div", "refusal refusal-" + (reason ? reason.tone : "system"));
    wrapper.append(icon(reason ? reason.icon : "warning"));
    const body = el("div");
    body.append(el("span", "refusal-category", reason ? reason.label : "No answer generated"));
    body.append(el("p", "refusal-text", data.refusal || data.reason || "No answer was generated."));
    wrapper.append(body);
    container.append(wrapper);

    const help = el("div", "refusal-help");
    if (data.refusal_reason === "medical_safety") {
      help.append(el("p", null, "Questions this corpus can answer"));
      const mention = PEPTIDE_MENTIONS.find((entry) => entry.pattern.test(state.question));
      if (mention) {
        [
          "What dose of " + mention.label + " was administered in the reported study?",
          "What adverse effects of " + mention.label + " have been reported?",
        ].forEach((text) => {
          const button = el("button", null, text);
          button.type = "button";
          button.addEventListener("click", () => { $("question").value = text; refreshCounter(); submit(); });
          help.append(button);
        });
      } else {
        help.append(el("p", "refusal-guidance",
          "Keep the peptide name in your question and ask what a named study reported, rather than what you should take."));
        const edit = el("button", null, "Edit the question");
        edit.type = "button";
        edit.addEventListener("click", () => { $("question").focus(); });
        help.append(edit);
      }
      container.append(help);
    } else if (data.refusal_reason === "insufficient_evidence") {
      help.append(el("p", null, "Try widening the search"));
      const wider = el("button", null, "Consult more records and ask again");
      wider.type = "button";
      wider.addEventListener("click", () => { $("records").value = "8"; refreshSummary(); submit(); });
      help.append(wider);
      const rephrase = el("button", null, "Rephrase the question");
      rephrase.type = "button";
      rephrase.addEventListener("click", () => { $("question").focus(); });
      help.append(rephrase);
      container.append(help);
    } else if (data.refusal_reason === "service_unavailable") {
      help.append(el("p", null, "Retrieval worked; only drafting failed"));
      const retry = el("button", null, "Try again");
      retry.type = "button";
      retry.addEventListener("click", () => submit());
      help.append(retry);
      container.append(help);
    } else if (data.refusal_reason === "budget_limit") {
      help.append(el("p", null, "Literature results still work"));
      const search = el("button", null, "Show ranked records for this question");
      search.type = "button";
      search.addEventListener("click", () => {
        const literature = document.querySelector('input[name="intent"][value="literature"]');
        if (literature) literature.checked = true;
        refreshSummary();
        submit();
      });
      help.append(search);
      container.append(help);
    }
  }

  /* Retrieval fails closed rather than downgrading silently: when the semantic
     index is absent, hybrid and semantic return no records and no fallback
     reason. Say that plainly instead of showing an unexplained empty result. */
  function renderRetrievalGap(requested, count) {
    if (count > 0) return false;
    if (requested !== "hybrid" && requested !== "semantic") return false;
    if (state.semanticAvailable === true) return false;
    const holder = $("fallback-notice");
    const notice = el("div", "fallback-notice");
    notice.append(icon("swap"));
    const body = el("div");
    body.append(el("strong", null,
      (MODE_LABELS[requested] || requested) + " retrieval returned no records."));
    body.append(el("span", null,
      "This deployment reports " + (state.semanticAvailable === false ? "that semantic retrieval is unavailable" :
        "that semantic retrieval may be unavailable") +
      ". Hybrid and semantic fail closed rather than quietly falling back, so nothing was retrieved."));
    const rerun = el("button", null, "Search again with keyword retrieval");
    rerun.type = "button";
    rerun.className = "button-secondary";
    rerun.addEventListener("click", () => {
      const answerKeyword = document.querySelector('input[name="answer-mode"][value="lexical"]');
      const literatureKeyword = document.querySelector('input[name="literature-mode"][value="bm25"]');
      if (intent() === "literature") { if (literatureKeyword) literatureKeyword.checked = true; }
      else if (answerKeyword) answerKeyword.checked = true;
      refreshSummary();
      submit();
    });
    body.append(rerun);
    notice.append(body);
    holder.append(notice);
    return true;
  }

  function renderFallback(requested, served, reason) {
    const holder = $("fallback-notice");
    clear(holder);
    if (!reason || !served || requested === served) return;
    const notice = el("div", "fallback-notice");
    notice.append(icon("swap"));
    const body = el("div");
    body.append(el("strong", null,
      "Searched with " + (MODE_LABELS[served] || served).toLowerCase() + " retrieval, not " +
      (MODE_LABELS[requested] || requested).toLowerCase() + "."));
    body.append(el("span", null, String(reason)));
    notice.append(body);
    holder.append(notice);
  }

  /* ---------- requests ---------- */

  async function postJSON(url, body) {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    let data = {};
    try { data = await response.json(); } catch (error) { data = {}; }
    if (!response.ok) {
      const detail = typeof data.detail === "string" ? data.detail : "";
      throw new Error(response.status === 429
        ? "Rate limit reached. Wait a moment and try again."
        : detail || "The request could not be completed.");
    }
    return data;
  }

  function showResult(question) {
    state.question = question;
    const result = $("result");
    result.hidden = false;
    $("asked-question").textContent = question;
  }

  function setMeta(kind, mode, items) {
    const meta = $("result-meta");
    clear(meta);
    const chip = el("span", "mode-chip", kind + " · " + (MODE_LABELS[mode] || mode));
    meta.append(chip);
    meta.append(el("span", null, evidenceScope(items).label));
  }

  function resetResultForRequest() {
    state.question = "";
    state.answerText = "";
    state.sources = [];
    $("answer-tools").hidden = true;
    $("result").hidden = true;
    clear($("answer-block"));
    clear($("result-meta"));
    clear($("fallback-notice"));
    clear($("sources-list"));
    clear($("evidence-body"));
    $("asked-question").textContent = "";
    $("evidence-details").open = false;
  }

  async function runAnswer(question) {
    const requested = answerMode();
    const data = await postJSON("/api/answer", {
      query: question, mode: requested, k: recordCount(),
    });

    const evidence = Array.isArray(data.evidence) ? data.evidence : [];
    const served = data.retrieval_mode || requested;
    showResult(question);
    setMeta("Evidence answer", served, evidence);
    renderFallback(data.requested_mode || requested, served, data.retrieval_fallback);
    const gapAnswer = renderRetrievalGap(requested, evidence.length);

    const block = $("answer-block");
    clear(block);
    if (data.answer) {
      renderAnswerText(block, data.answer, data.citations);
      state.answerText = String(data.answer);
      $("answer-tools").hidden = false;
    } else {
      renderRefusal(block, data);
      state.answerText = "";
      $("answer-tools").hidden = true;
    }

    const citations = Array.isArray(data.citations) ? data.citations : [];
    if (data.answer && citations.length) {
      state.sources = groupCitations(citations);
      renderSources(state.sources, "Cited sources");
    } else {
      state.sources = groupRetrievedSources(evidence);
      renderSources(state.sources, "Retrieved sources");
    }

    renderEvidence(evidence);
    $("evidence-details").open = false;

    if (data.answer) {
      setStatus("Answer ready. " + evidenceScope(evidence).label + ".");
    } else if (gapAnswer) {
      setStatus((MODE_LABELS[requested] || requested) + " retrieval is not enabled here, so no records were retrieved.");
    } else {
      const reason = REFUSALS[data.refusal_reason];
      setStatus((reason ? reason.label : "No answer generated") + ". Retrieved evidence is shown.");
    }
  }

  async function runLiterature(question) {
    const requested = literatureMode();
    const data = await postJSON("/api/search", {
      query: question, mode: requested, k: 10,
    });

    const results = Array.isArray(data.results) ? data.results : [];
    const served = data.mode || requested;
    showResult(question);
    setMeta("Literature results", served, results);
    renderFallback(data.requested_mode || requested, served, data.fallback_reason);
    renderRetrievalGap(requested, results.length);

    const block = $("answer-block");
    clear(block);
    const notice = el("div", "refusal refusal-boundary");
    notice.append(icon("search"));
    const body = el("div");
    body.append(el("span", "refusal-category", "Records only"));
    body.append(el("p", "refusal-text",
      "No answer is generated in this view. " + (MODE_LABELS[served] || served) +
      " retrieval ranks records; it does not read or summarize them."));
    notice.append(body);
    block.append(notice);

    const help = el("div", "refusal-help");
    help.append(el("p", null, "Prefer a written answer?"));
    const ask = el("button", null, "Ask for an evidence answer instead");
    ask.type = "button";
    ask.addEventListener("click", () => {
      const answer = document.querySelector('input[name="intent"][value="answer"]');
      if (answer) answer.checked = true;
      refreshSummary();
      submit();
    });
    help.append(ask);
    block.append(help);

    state.answerText = "";
    $("answer-tools").hidden = true;
    state.sources = groupRetrievedSources(results);
    renderSources(state.sources, "Ranked records");
    renderEvidence(results);
    $("evidence-details").open = false;
    setStatus(evidenceScope(results).label + ".");
  }

  async function submit() {
    if (state.pending) return;
    const question = $("question").value.trim();
    if (!question) {
      setStatus("Enter a question first.");
      $("question").focus();
      return;
    }
    state.pending = true;
    $("ask-button").disabled = true;
    // A failed rerun must never leave answer A visible under question B's input.
    resetResultForRequest();
    const literature = intent() === "literature";
    setStatus(literature ? "Searching 2,000 records…" : "Searching 2,000 records, then reading the retrieved abstracts…");
    try {
      if (literature) await runLiterature(question);
      else await runAnswer(question);
      bringIntoView($("result"), "start");
      $("result-heading").focus({ preventScroll: true });
    } catch (error) {
      setStatus(error && error.message ? error.message : "The request could not be completed.", true);
    } finally {
      state.pending = false;
      $("ask-button").disabled = false;
    }
  }

  /* ---------- finishing features ---------- */

  function copyText() {
    if (!state.answerText) return "";
    const lines = [state.answerText, "", "Sources:"];
    state.sources.forEach((source) => {
      lines.push("[" + source.n + "] " + source.title + (source.url ? " — " + source.url : ""));
    });
    lines.push("", "Question: " + state.question);
    lines.push("Research use only. This tool does not provide medical advice.");
    return lines.join("\n");
  }

  function shareUrl() {
    return location.origin + location.pathname + "#q=" + encodeURIComponent(state.question || $("question").value.trim());
  }

  async function writeClipboard(value, okMessage) {
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      setStatus(okMessage);
    } catch (error) {
      setStatus("Copying is blocked in this browser. Select the text manually.", true);
    }
  }

  function prefillFromHash() {
    const hash = location.hash || "";
    const match = /^#q=(.*)$/.exec(hash);
    if (!match) return;
    let question = "";
    try { question = decodeURIComponent(match[1].replace(/\+/g, " ")); } catch (error) { return; }
    question = question.slice(0, MAX_QUESTION).trim();
    if (!question) return;
    // Prefill only. A shared link must never spend a request on the recipient.
    $("question").value = question;
    refreshCounter();
    setStatus("Question loaded from a shared link. Press Ask Peptide Evidence to run it.");
  }

  /* ---------- explorer and metrics ---------- */

  function renderTopics(topics) {
    const grid = $("topic-grid");
    clear(grid);
    topics.forEach((topic) => {
      const details = el("details", "topic");
      const summary = el("summary");
      const name = el("span", "topic-name");
      name.append(el("b", null, topic.name));
      name.append(el("span", null, topic.subtitle || ""));
      summary.append(name);
      summary.append(icon("arrow", "chevron"));
      details.append(summary);

      const list = el("div", "topic-questions");
      (topic.questions || []).forEach((question) => {
        const button = el("button");
        button.type = "button";
        button.append(icon("arrow"));
        button.append(el("span", null, question));
        button.addEventListener("click", () => {
          $("question").value = question;
          refreshCounter();
          bringIntoView($("question"), "center");
          submit();
        });
        list.append(button);
      });
      details.append(list);

      details.addEventListener("toggle", () => {
        if (!details.open) return;
        grid.querySelectorAll("details.topic[open]").forEach((other) => {
          if (other !== details) other.open = false;
        });
      });
      grid.append(details);
    });
  }

  async function loadExamples() {
    try {
      const response = await fetch("/api/examples");
      const data = await response.json();
      if (data && data.available && Array.isArray(data.topics) && data.topics.length) {
        renderTopics(data.topics);
        return;
      }
    } catch (error) { /* fall through to the empty notice */ }
    $("explorer-empty").hidden = false;
  }

  function metricTile(value, label, note) {
    const tile = el("div", "metric");
    tile.append(el("span", "metric-value", value));
    tile.append(el("span", "metric-label", label));
    tile.append(el("span", "metric-note", note));
    return tile;
  }

  const decimals = (value) => (typeof value === "number" && Number.isFinite(value) ? value.toFixed(3) : null);

  async function loadMetrics() {
    const grid = $("metrics-grid");
    const note = $("metrics-note");
    try {
      const response = await fetch("/api/metrics");
      const payload = await response.json();
      const metrics = (payload && payload.metrics) || {};
      const measured = metrics.measured_ir || null;
      if (typeof metrics.semantic_available === "boolean") state.semanticAvailable = metrics.semantic_available;
      clear(grid);

      if (typeof metrics.corpus_documents === "number") {
        grid.append(metricTile(metrics.corpus_documents.toLocaleString("en-US"), "Records indexed",
          "PubMed abstracts in the frozen corpus"));
      }
      const holdout = measured && measured.untouched_holdout;
      const all = measured && measured.all_queries;
      if (holdout) {
        const count = holdout.query_count;
        if (decimals(holdout.mrr)) grid.append(metricTile(decimals(holdout.mrr), "MRR",
          "Untouched holdout, " + count + " queries"));
        if (decimals(holdout.recall_at_10)) grid.append(metricTile(decimals(holdout.recall_at_10), "Recall@10",
          "Untouched holdout, " + count + " queries"));
        if (decimals(holdout.ndcg_at_10)) grid.append(metricTile(decimals(holdout.ndcg_at_10), "NDCG@10",
          "Untouched holdout, " + count + " queries"));
      }
      if (!grid.childNodes.length) {
        note.textContent = "Measured retrieval numbers are unavailable for this build.";
        return;
      }
      const parts = [];
      if (holdout) {
        parts.push("The holdout queries were never used for tuning, so they are the honest score. " +
          "Across all " + (all ? all.query_count : "evaluated") + " judged queries the tuned system reaches Recall@10 " +
          (decimals(all && all.recall_at_10) || "—") + " and NDCG@10 " + (decimals(all && all.ndcg_at_10) || "—") + ".");
      }
      parts.push("Retrieval is scored; answers are separately judged for faithfulness and citation correctness.");
      if (metrics.semantic_available === false) parts.push("Semantic and hybrid retrieval are not enabled on this deployment. They return no records rather than falling back, so use Keyword retrieval here.");
      if (metrics.generation_available === false) parts.push("Answer generation is not enabled on this deployment; requests return retrieved evidence only.");
      note.textContent = parts.join(" ");
    } catch (error) {
      clear(grid);
      note.textContent = "Measured retrieval numbers could not be loaded.";
    }
  }

  /* ---------- wiring ---------- */

  function init() {
    $("ask-form").addEventListener("submit", (event) => { event.preventDefault(); submit(); });

    $("question").addEventListener("input", refreshCounter);
    $("question").addEventListener("keydown", (event) => {
      if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
      event.preventDefault();
      submit();
    });

    document.querySelectorAll('input[name="intent"], input[name="answer-mode"], input[name="literature-mode"]')
      .forEach((input) => input.addEventListener("change", refreshSummary));
    $("records").addEventListener("input", () => {
      $("records-output").textContent = $("records").value;
      refreshSummary();
    });

    $("edit-button").addEventListener("click", () => {
      $("question").focus();
      $("question").setSelectionRange($("question").value.length, $("question").value.length);
      bringIntoView($("question"), "center");
    });
    $("copy-button").addEventListener("click", () => writeClipboard(copyText(), "Answer and citations copied."));
    $("share-button").addEventListener("click", () => {
      const url = shareUrl();
      if (!state.question && !$("question").value.trim()) {
        setStatus("Enter a question before sharing.");
        return;
      }
      location.hash = "q=" + encodeURIComponent(state.question || $("question").value.trim());
      writeClipboard(url, "Share link copied. It prefills the question without running it.");
    });
    $("back-to-topics").addEventListener("click", () => {
      bringIntoView($("explorer"), "start");
    });

    refreshCounter();
    refreshSummary();
    prefillFromHash();
    loadExamples();
    loadMetrics();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
