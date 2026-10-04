// Course Finder search page. Plain JavaScript: no framework, no build step.
// It calls the same JSON API any other client uses: /api/v1/courses and /api/v1/stats.
// Course data is only ever written with textContent, never innerHTML, so text from
// the database can never be turned into markup or script.

const API = "/api/v1";
const PER_PAGE = 20;
const FILTERS = ["q", "country", "level", "intake", "max_fee", "sort"];
const DEFAULT_SORT = "title";
const COUNTRY_NAMES = { UK: "United Kingdom", CA: "Canada" };
const CURRENCIES = { UK: "GBP", CA: "CAD" };

const form = document.getElementById("search-form");
const maxFee = form.elements.max_fee;
const maxFeeLabel = document.getElementById("max-fee-label");
const maxFeeHint = document.getElementById("max-fee-hint");
const statusLine = document.getElementById("status");
const results = document.getElementById("results");
const resultsHeading = document.getElementById("results-heading");
const pager = document.getElementById("pager");
const prevButton = document.getElementById("prev");
const nextButton = document.getElementById("next");
const pageInfo = document.getElementById("page-info");
const cardTemplate = document.getElementById("course-card");

let page = 1;
let debounceTimer;
let inFlight; // AbortController for the request currently running

// ------------------------------------------------------------ URL <-> form

// Filters live in the URL, so a search survives a refresh and can be shared.
function readFiltersFromUrl() {
  const params = new URLSearchParams(window.location.search);
  for (const name of FILTERS) {
    form.elements[name].value = params.get(name) ?? (name === "sort" ? DEFAULT_SORT : "");
  }
  page = Math.max(1, Number.parseInt(params.get("page"), 10) || 1);
}

function filtersAsParams() {
  const params = new URLSearchParams();
  for (const name of FILTERS) {
    const value = form.elements[name].value.trim();
    if (value && !(name === "sort" && value === DEFAULT_SORT)) params.set(name, value);
  }
  if (page > 1) params.set("page", page);
  return params;
}

// The API rejects max_fee without a country (UK fees are GBP, Canadian fees CAD),
// so the field only unlocks once a country is chosen, and shows its currency.
function syncMaxFeeField() {
  const currency = CURRENCIES[form.elements.country.value];
  maxFee.disabled = !currency;
  if (!currency) maxFee.value = "";
  maxFeeLabel.textContent = currency ? `Max fee (${currency})` : "Max fee";
  maxFeeHint.hidden = Boolean(currency);
}

// ------------------------------------------------------------ formatting

function formatMoney(amount, currency) {
  const value = Number(amount); // the API sends money as a string, e.g. "18500.00"
  const digits = Number.isInteger(value) ? 0 : 2;
  return new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency,
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

function formatDate(iso) {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function formatDuration(months, studyMode) {
  const mode = studyMode === "part_time" ? "part time" : "full time";
  if (!months) return mode;
  const length = months % 12 === 0
    ? `${months / 12} year${months === 12 ? "" : "s"}`
    : `${months} months`;
  return `${length}, ${mode}`;
}

// ------------------------------------------------------------ rendering

function showStatus(message, isError = false) {
  statusLine.textContent = message;
  statusLine.classList.toggle("error", isError);
}

function courseCard(course) {
  const card = cardTemplate.content.firstElementChild.cloneNode(true);
  const fill = (field, text) => {
    card.querySelector(`[data-field="${field}"]`).textContent = text;
  };
  const university = course.university;

  fill("level", course.level);
  fill("title", course.title);
  fill("university", university.name);
  fill("location", [university.city, COUNTRY_NAMES[university.country]].filter(Boolean).join(", "));
  fill("fee", formatMoney(course.tuition_fee_international, course.currency));
  fill("ielts", course.ielts_min ?? "Not stated");
  fill("intakes", course.intakes.length ? course.intakes.join(", ") : "Not stated");
  fill("duration", formatDuration(course.duration_months, course.study_mode));

  const verified = card.querySelector('[data-field="verified"]');
  if (course.last_verified_at) {
    verified.textContent = formatDate(course.last_verified_at);
    verified.setAttribute("datetime", course.last_verified_at);
  } else {
    verified.textContent = "never";
  }
  return card;
}

function render({ data, meta }) {
  results.replaceChildren(...data.map(courseCard));

  if (meta.total === 0) {
    showStatus("No courses match these filters.");
  } else {
    const first = (meta.page - 1) * meta.per_page + 1;
    const last = first + data.length - 1;
    const noun = meta.total === 1 ? "course" : "courses";
    showStatus(`Showing ${first} to ${last} of ${meta.total} ${noun}`);
  }

  pager.hidden = meta.pages <= 1;
  prevButton.disabled = meta.page <= 1;
  nextButton.disabled = meta.page >= meta.pages;
  pageInfo.textContent = `Page ${meta.page} of ${meta.pages}`;
}

// ------------------------------------------------------------ fetching

async function search() {
  const params = filtersAsParams();
  history.replaceState(null, "", params.size ? `?${params}` : window.location.pathname);

  // Cancel the previous request, so a slow old response can never overwrite a
  // newer one (e.g. typing "dat" then "data" quickly).
  inFlight?.abort();
  const controller = new AbortController();
  inFlight = controller;

  showStatus("Loading courses…");
  results.setAttribute("aria-busy", "true");
  try {
    params.set("per_page", PER_PAGE);
    const response = await fetch(`${API}/courses?${params}`, { signal: controller.signal });
    const body = await response.json().catch(() => null); // e.g. an HTML 502 from a proxy
    if (!response.ok) {
      // On a 400, the API's message names the problem, e.g. "max_fee: Input should be ...".
      throw new Error(body?.error?.message ?? `The server returned an error (${response.status}).`);
    }

    // A shared link can point past the last page if the data has since shrunk.
    if (body.data.length === 0 && body.meta.total > 0) {
      page = body.meta.pages;
      return search();
    }
    render(body);
  } catch (error) {
    if (error.name === "AbortError") return; // replaced by a newer search
    results.replaceChildren();
    pager.hidden = true;
    const message = error instanceof TypeError
      ? "Couldn't reach the server. Check your connection and try again."
      : error.message;
    showStatus(message, true);
  } finally {
    if (inFlight === controller) results.removeAttribute("aria-busy");
  }
}

async function loadStats() {
  const strip = document.getElementById("stats-strip");
  try {
    const response = await fetch(`${API}/stats`);
    if (!response.ok) return; // the footer is a nice-to-have; never block the page on it
    const { data } = await response.json();
    const countries = Object.keys(data.courses_by_country).length;
    const run = data.latest_ingestion;
    const parts = [
      `${data.total_courses} courses`,
      `${countries} ${countries === 1 ? "country" : "countries"}`,
    ];
    if (run) parts.push(`data last ingested ${formatDate(run.finished_at ?? run.started_at)}`);
    strip.textContent = parts.join(" · ");
  } catch {
    // Same as above: leave the strip empty.
  }
}

// ------------------------------------------------------------ events

function newSearch() {
  clearTimeout(debounceTimer);
  page = 1;
  search();
}

function goToPage(newPage) {
  page = newPage;
  search();
  resultsHeading.focus(); // moves keyboard and screen-reader users back to the top of the results
}

// Typing waits until the user pauses for 300 ms, so we don't send a request per keystroke.
form.addEventListener("input", (event) => {
  if (event.target.matches("input")) {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(newSearch, 300);
  }
});

// Dropdowns search straight away.
form.addEventListener("change", (event) => {
  if (!event.target.matches("select")) return;
  if (event.target.name === "country") syncMaxFeeField();
  newSearch();
});

form.addEventListener("submit", (event) => {
  event.preventDefault(); // Enter searches immediately instead of reloading the page
  newSearch();
});

document.getElementById("clear").addEventListener("click", () => {
  form.reset();
  syncMaxFeeField();
  newSearch();
});

prevButton.addEventListener("click", () => goToPage(page - 1));
nextButton.addEventListener("click", () => goToPage(page + 1));

// ------------------------------------------------------------ start

readFiltersFromUrl();
syncMaxFeeField();
search();
loadStats();
