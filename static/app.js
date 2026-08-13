(() => {
  const $ = (id) => document.getElementById(id);
  let lastResults = [];
  function text(node, value) { node.textContent = value == null ? "" : String(value); }
  function status(message, error = false) { const node = $("status"); text(node, message); node.className = error ? "status error" : "status"; }
  function clear(node) { node.replaceChildren(); }
  function highlighted(node, value) {
    const source = value == null ? "" : String(value);
    const marker = /\[\[([^\]]+)\]\]/g;
    let cursor = 0;
    for (const match of source.matchAll(marker)) {
      node.append(document.createTextNode(source.slice(cursor, match.index)));
      const emphasis = document.createElement("mark");
      text(emphasis, match[1]);
      node.append(emphasis);
      cursor = match.index + match[0].length;
    }
    node.append(document.createTextNode(source.slice(cursor)));
  }
  function evidenceCard(item) {
    const card = document.createElement("article"); card.className = "result";
    const title = document.createElement("h3"); text(title, item.title); card.append(title);
    const snippet = document.createElement("p"); highlighted(snippet, item.snippet); card.append(snippet);
    if (item.pubmed_url) { const link = document.createElement("a"); link.href = item.pubmed_url; link.target = "_blank"; link.rel = "noopener noreferrer"; text(link, `PubMed ${item.pmid}`); card.append(link); }
    return card;
  }
  function renderResults(items) { const list = $("result-list"); clear(list); if (!items.length) { text(list, "No matching evidence was returned."); return; } items.forEach((item) => list.append(evidenceCard(item))); }
  async function request(url, body) { const response = await fetch(url, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)}); const data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data.detail || "Request failed"); return data; }
  function query() { return $("query").value; }
  function mode() { return $("mode").value; }
  $("search").addEventListener("click", async () => { try { status("Searching..."); const data = await request("/api/search", {query: query(), mode: mode(), k: 10}); lastResults = data.results || []; renderResults(lastResults); status(`${lastResults.length} evidence record(s) found.`); } catch (e) { status(e.message, true); } });
  $("answer-button").addEventListener("click", async () => { try { status("Preparing an evidence-based response..."); let answerMode = mode(); if (answerMode === "boolean" || answerMode === "bm25") answerMode = "lexical"; const data = await request("/api/answer", {query: query(), mode: answerMode, k: 5}); const content = $("answer-content"); clear(content); const response = document.createElement("p"); text(response, data.answer || data.refusal || data.reason || "No answer was generated."); content.append(response); if (data.citations && data.citations.length) { const citations = document.createElement("p"); citations.append(document.createTextNode("Citations: ")); data.citations.forEach((citation, index) => { if (index) citations.append(document.createTextNode(", ")); if (citation && citation.pubmed_url) { const link = document.createElement("a"); link.href = citation.pubmed_url; link.target = "_blank"; link.rel = "noopener noreferrer"; text(link, `[${citation.citation_id}] PMID ${citation.pmid}`); citations.append(link); } else { citations.append(document.createTextNode(String(citation))); } }); content.append(citations); } const evidence = $("answer-evidence"); clear(evidence); (data.evidence || lastResults).forEach((item) => evidence.append(evidenceCard(item))); status(data.retrieval_only ? "Retrieval-only response." : "Answer ready."); } catch (e) { status(e.message, true); } });
  $("metrics-button").addEventListener("click", async () => { try { const response = await fetch("/api/metrics"); const data = await response.json(); text($("metrics-content"), JSON.stringify(data.metrics, null, 2)); } catch (e) { status(e.message, true); } });
  document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => { document.querySelectorAll(".tab,.panel").forEach((node) => node.classList.remove("active")); tab.classList.add("active"); $(tab.dataset.tab).classList.add("active"); }));
})();
