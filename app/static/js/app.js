/* The little bits of behaviour the pages need. Nothing more. */

// The six code boxes jump along as you type, and a pasted code fills them all.
(function code() {
  const box = document.getElementById("code");
  if (!box) return;
  const inputs = Array.from(box.querySelectorAll("input"));

  inputs.forEach((input, i) => {
    input.addEventListener("input", () => {
      input.value = input.value.replace(/\D/g, "").slice(0, 1);
      if (input.value && i < inputs.length - 1) inputs[i + 1].focus();
    });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Backspace" && !input.value && i > 0) inputs[i - 1].focus();
    });
    input.addEventListener("paste", (e) => {
      const digits = (e.clipboardData.getData("text") || "").replace(/\D/g, "");
      if (!digits) return;
      e.preventDefault();
      inputs.forEach((f, n) => { f.value = digits[n] || ""; });
      inputs[Math.min(digits.length, inputs.length - 1)].focus();
    });
  });
})();

// A chat opens at the newest message, not at the oldest.
(function thread() {
  const thread = document.getElementById("thread");
  if (!thread) return;
  window.scrollTo(0, document.body.scrollHeight);
})();

// The new entry sheet shows what you picked, so you see it before you publish.
(function preview() {
  const field = document.getElementById("photos");
  if (!field) return;
  const slots = Array.from(document.querySelectorAll("[data-slot]"));
  field.addEventListener("change", () => {
    const files = Array.from(field.files || []);
    slots.forEach((slot, i) => {
      slot.innerHTML = "";
      if (!files[i]) return;
      const img = document.createElement("img");
      img.src = URL.createObjectURL(files[i]);
      img.alt = "";
      slot.appendChild(img);
    });
  });
})();

// A dropdown whose first entry is only a hint. A browser draws the chosen
// entry in the open list even when that entry is hidden, so the hint stood
// there with a tick next to it as if it were a programme you could study.
// The answer is to take it out of the list for as long as the list is open
// and put it back if nothing was chosen, so the closed field still has
// something to say.
(function hintOption() {
  document.querySelectorAll("select").forEach((picker) => {
    const hint = picker.querySelector("option[data-hint]");
    if (!hint) return;

    const lift = () => {
      if (!hint.parentNode || picker.value !== "") return;
      hint.remove();
      picker.selectedIndex = -1;
    };
    const drop = () => {
      if (hint.parentNode || picker.value !== "") return;
      picker.insertBefore(hint, picker.firstChild);
      picker.selectedIndex = 0;
    };

    // mousedown and keydown both run before the list is drawn. change and
    // blur are the two ways back out of it.
    picker.addEventListener("mousedown", lift);
    picker.addEventListener("keydown", lift);
    picker.addEventListener("change", drop);
    picker.addEventListener("blur", drop);
  });
})();

// The password rules, checked while you type. Nothing turns red before the
// first character, because a form that is red the moment it opens is not
// telling you anything you did wrong.
(function password() {
  const field = document.getElementById("password");
  const again = document.getElementById("password2");
  const note = document.getElementById("pw-rules");
  if (!field || !note) return;

  const rules = note.textContent.trim();
  const needs = [
    [(v) => v.length >= 8, "8 characters"],
    [(v) => /[A-Z]/.test(v), "a capital letter"],
    [(v) => /[0-9]/.test(v), "a number"],
    [(v) => /[^A-Za-z0-9]/.test(v), "a special character"],
  ];

  // a, b and c. The last one gets the and, which is how a person says it.
  function spoken(parts) {
    if (parts.length === 1) return parts[0];
    return parts.slice(0, -1).join(", ") + " and " + parts[parts.length - 1];
  }

  function say(text, bad) {
    note.textContent = text;
    note.classList.toggle("rules--bad", Boolean(bad));
  }

  function check() {
    const value = field.value;
    const repeat = again ? again.value : "";

    if (!value) {
      field.classList.remove("input--bad");
      if (again) again.classList.remove("input--bad");
      say(rules, false);
      return;
    }

    const missing = needs.filter((n) => !n[0](value)).map((n) => n[1]);
    field.classList.toggle("input--bad", missing.length > 0);

    if (missing.length) {
      if (again) again.classList.remove("input--bad");
      say("Still missing " + spoken(missing) + ".", true);
      return;
    }
    if (repeat && repeat !== value) {
      if (again) again.classList.add("input--bad");
      say("The two passwords are not the same.", true);
      return;
    }
    if (again) again.classList.remove("input--bad");
    say(repeat ? "That password works." : rules, false);
  }

  field.addEventListener("input", check);
  if (again) again.addEventListener("input", check);
  check();
})();

// The course list is long, so it filters while you type and keeps a count.
(function courses() {
  const field = document.getElementById("filter");
  const list = document.getElementById("list");
  if (!field || !list) return;

  const rows = Array.from(list.querySelectorAll(".pick"));
  const nothing = document.getElementById("nothing");
  const picked = document.getElementById("picked");
  const programmePicker = document.getElementById("programme");
  const cemsPicker = document.getElementById("cems_programme");
  const missingProgramme = document.getElementById("no-programme-courses");
  const courseHeadings = list.querySelectorAll(".course-heading");

  // What a course is to the programme you picked, in the order you want to
  // read them. Your own compulsory ones first, then the ones you may choose,
  // then everything else the school lets you sit in on.
  const RANK = { MANDATORY: 0, EXCLUSIVE_ELECTIVE: 1, ELECTIVE: 2, OUT_PROGRAM: 3 };
  const SAYS = {
    MANDATORY: "mandatory",
    EXCLUSIVE_ELECTIVE: "elective",
    ELECTIVE: "elective",
    OUT_PROGRAM: "outside your programme",
  };

  // Read once. There are a couple of hundred rows and the list is sorted
  // again on every change of programme, so reading the same text out of the
  // same attribute each time would be hundreds of needless reads.
  const sheet = rows.map((row, place) => ({
    row: row,
    place: place,
    types: JSON.parse(row.dataset.programmes || "{}"),
  }));

  function count() {
    const n = rows.filter((r) => r.querySelector("input").checked).length;
    picked.textContent = n === 1 ? "1 picked" : n + " picked";
  }

  function lastLine() {
    const visible = rows.filter((r) => !r.hidden);
    rows.forEach((r) => r.classList.remove("last"));
    if (visible.length) visible[visible.length - 1].classList.add("last");
  }

  // Put the rows in the order of that programme. Inside one rank they keep
  // the order they arrived in, which is alphabetical, so the list never
  // jumps about for no reason.
  let sortedFor = null;
  function reorder(programme) {
    if (programme === sortedFor) return;
    sortedFor = programme;
    const rank = (entry) => {
      const seat = programme ? RANK[entry.types[programme]] : undefined;
      return seat === undefined ? 9 : seat;
    };
    const order = sheet.slice().sort(
      (a, b) => rank(a) - rank(b) || a.place - b.place);
    const box = document.createDocumentFragment();
    order.forEach((entry) => box.appendChild(entry.row));
    list.appendChild(box);
  }

  const updateFilter = () => {
    const q = field.value.trim().toLowerCase();
    let shown = 0;
    const programme = programmePicker
      ? (programmePicker.value === "CEMS Master in Management" ? cemsPicker.value : programmePicker.value)
      : null;
    if (programmePicker) reorder(programme);
    sheet.forEach((entry) => {
      const row = entry.row;
      let fitsProgramme = true;
      if (programmePicker) {
        const type = programme ? entry.types[programme] : null;
        fitsProgramme = Boolean(type);
        const badge = row.querySelector(".course-type");
        if (badge) badge.textContent = type ? " · " + (SAYS[type] || "") : "";
      }
      const hit = fitsProgramme && (!q || row.dataset.text.includes(q));
      row.hidden = !hit;
      if (hit) shown += 1;
    });
    courseHeadings.forEach((heading) => {
      const siblings = [];
      for (let sibling = heading.nextElementSibling; sibling && !sibling.classList.contains("course-heading"); sibling = sibling.nextElementSibling) {
        if (sibling.classList.contains("pick")) siblings.push(sibling);
      }
      heading.hidden = !siblings.some((row) => !row.hidden);
    });
    const waiting = Boolean(programmePicker) && !programme;
    if (missingProgramme) missingProgramme.hidden = !waiting;
    list.hidden = shown === 0;
    // Nothing matches is only worth saying once there is a programme to
    // match inside. Before that the line above already says what to do.
    nothing.hidden = shown !== 0 || waiting;
    lastLine();
  };
  field.addEventListener("input", updateFilter);
  if (programmePicker) programmePicker.addEventListener("change", updateFilter);
  if (cemsPicker) cemsPicker.addEventListener("change", updateFilter);

  list.addEventListener("change", count);
  count();
  updateFilter();
})();

// On the edit page, picking CEMS asks which master it sits on top of, and a
// chosen picture is shown straight away.
(function editProfile() {
  const programme = document.getElementById("programme");
  const base = document.getElementById("cems-base");
  if (programme && base) {
    const cems = base.dataset.cems || "CEMS Master in Management";
    const sync = () => { base.hidden = programme.value !== cems; };
    programme.addEventListener("change", sync);
    sync();
  }

  const photo = document.getElementById("photo");
  const slot = document.getElementById("photo-slot");
  if (photo && slot) {
    photo.addEventListener("change", () => {
      const file = (photo.files || [])[0];
      if (!file) return;
      const img = document.createElement("img");
      img.src = URL.createObjectURL(file);
      img.alt = "";
      const box = slot.querySelector(".avatar");
      box.textContent = "";
      box.appendChild(img);
    });
  }
})();

// The heart fills in on the spot and the number next to it counts along, so
// saving something never takes you away from what you were looking at.
(function save() {
  const form = document.querySelector(".save-form");
  if (!form) return;
  const button = form.querySelector("button");
  const line = document.getElementById("saves");
  const count = line ? line.querySelector("[data-count]") : null;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    let data;
    try {
      const answer = await fetch(form.action, {
        method: "POST",
        headers: { Accept: "application/json" },
      });
      data = await answer.json();
    } catch (err) {
      form.submit();   // no connection, let the page do it the plain way
      return;
    }

    button.classList.toggle("save--on", data.saved);
    button.setAttribute("aria-pressed", data.saved ? "true" : "false");
    button.setAttribute("aria-label", data.saved ? "Saved" : "Save this");
    const heart = button.querySelector("svg path");
    if (heart) heart.setAttribute("fill", data.saved ? "currentColor" : "none");
    if (line && count) {
      count.textContent = data.count;
      line.hidden = data.count === 0;
    }
    button.classList.remove("save--pop");
    void button.offsetWidth;          // start the animation again from zero
    button.classList.add("save--pop");
  });
})();

// Picking a sort or a filter on Market loads the list straight away, so there
// is no Apply button anywhere to look for.
(function filters() {
  const form = document.querySelector("form[data-auto]");
  if (!form) return;

  form.addEventListener("change", () => {
    // A filter set to nothing has no business standing in the address, so it
    // is switched off first and then left out of what gets sent.
    form.querySelectorAll("select, input").forEach((field) => {
      const off = field.type === "checkbox" ? !field.checked : !field.value;
      if (off) field.disabled = true;
    });
    form.submit();
  });
})();

// The capsule under the tab bar. It is measured off the tab it belongs to
// rather than worked out from the padding, so it fits exactly whatever the
// bar happens to be doing. Moving between tabs is a real page load here, so
// the slide happens on arrival. The page works out which tab you came from
// and plays the capsule travelling from there.
//
// Two things are deliberate. The final position is set first and the travel
// is an animation on top, so a throttled page still leaves the capsule in
// the right place rather than stranded where it started. And a measurement
// of zero is thrown away, because a page sitting in a background tab is not
// laid out at all and every rectangle in it comes back empty. Writing that
// down would shrink the capsule to a dot in the top left corner, which is
// exactly what it used to do.
(function tabglide() {
  const bar = document.querySelector(".tabbar");
  const glide = bar && bar.querySelector(".glide");
  if (!glide) return;

  const tabs = Array.from(bar.querySelectorAll(".tab"));
  const here = tabs.findIndex((t) => t.getAttribute("aria-current") === "page");
  if (here < 0) return;

  function boxOf(n) {
    const tab = tabs[n].getBoundingClientRect();
    const rail = bar.getBoundingClientRect();
    // clientLeft and clientTop are the bar's own border. A child placed at
    // zero starts inside it, so without them the capsule sits one pixel low,
    // which is exactly the thickness of the line above the bar.
    return {
      w: tab.width, h: tab.height,
      x: tab.left - rail.left - bar.clientLeft,
      y: tab.top - rail.top - bar.clientTop,
    };
  }

  // Which tab you came from. A reload, a listing or the first visit all
  // count as no journey, and then the capsule simply sits still.
  let from = -1;
  if (document.referrer) {
    try {
      const came = new URL(document.referrer).pathname;
      from = tabs.findIndex((t) => new URL(t.href).pathname === came);
    } catch (err) {
      from = -1;
    }
  }

  const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let arrived = false;

  function settle() {
    const to = boxOf(here);
    if (!to.w) return;   // no layout yet, leave what the stylesheet placed

    glide.style.left = "0px";
    glide.style.top = "0px";
    glide.style.width = to.w + "px";
    glide.style.height = to.h + "px";
    glide.style.transform = "translate(" + to.x + "px," + to.y + "px)";

    if (arrived) return;
    arrived = true;

    if (from >= 0 && from !== here && !still && glide.animate
        && document.visibilityState === "visible") {
      const was = boxOf(from);
      const run = glide.animate(
        [{ transform: "translate(" + was.x + "px," + was.y + "px)" },
         { transform: "translate(" + to.x + "px," + to.y + "px)" }],
        // A touch of overshoot at the end. A straight slide reads as a cheap
        // animation, the small settle is what makes it feel physical.
        { duration: 420, easing: "cubic-bezier(0.34, 1.56, 0.64, 1)" }
      );
      run.finished.catch(() => {});

      // A page put in the background has its animations frozen where they
      // stand, and ours would stand on the tab you came from. This timer is
      // frozen with it and goes off the moment the page is awake again, so
      // the capsule lands instead of sitting on the wrong tab. On a page
      // nobody left alone, the animation is long over before it fires.
      setTimeout(() => {
        if (run.playState === "running") run.finish();
      }, 1200);
    }
  }

  settle();

  // The layout can turn up later than this script does. A tab in the
  // background is not laid out until somebody looks at it, a window can
  // change size, and a page can come back out of the browser's cache. Each
  // of those is a moment the measurement is worth taking again.
  if (window.ResizeObserver) new ResizeObserver(settle).observe(bar);

  document.addEventListener("visibilitychange", () => {
    // A page that is put in the background has its animations frozen where
    // they stand, which for us is the tab you came from. Jumping them to
    // the end first means the capsule is on the right tab the moment you
    // look again, whether or not the browser ever resumes them.
    if (document.hidden) {
      glide.getAnimations().forEach((run) => run.finish());
    }
    settle();
  });
  window.addEventListener("pageshow", settle);
  window.addEventListener("resize", settle);
})();

// The confirmation after publishing or closing fades away on its own, and the
// ?done=... leaves the address so a reload does not show it again.
(function toast() {
  const t = document.getElementById("toast");
  if (!t) return;
  const url = new URL(window.location.href);
  url.searchParams.delete("done");
  history.replaceState(null, "", url.pathname + url.search + url.hash);
  setTimeout(() => {
    t.classList.add("toast--out");
    t.addEventListener("animationend", () => t.remove(), { once: true });
  }, 3200);
})();

// The housing link on the new entry form. While you type it says which site
// it recognised, offers to open it so you can check it is the right place,
// and stops the form from going off with a link we would refuse anyway.
(function housingLink() {
  const box = document.querySelector(".linkfield");
  if (!box) return;
  const field = box.querySelector("input");
  const status = box.querySelector(".linkfield-status");
  const platforms = JSON.parse(box.dataset.platforms || "[]");
  const names = box.dataset.names || "";
  const hint = status.innerHTML;

  function recognise(text) {
    text = text.trim();
    if (!text || /\s/.test(text)) return null;
    let url;
    try { url = new URL(text.includes("://") ? text : "https://" + text); }
    catch (e) { return null; }
    if (!/^https?:$/.test(url.protocol) || url.username || url.password) return null;
    if (url.port && url.port !== "443" && url.port !== "80") return null;
    const host = url.hostname.toLowerCase().replace(/\.$/, "");
    for (const [domain, name] of platforms) {
      if (host === domain || host.endsWith("." + domain)) {
        url.protocol = "https:"; url.port = ""; url.hash = "";
        return { name, href: url.toString() };
      }
    }
    return null;
  }

  function update() {
    const text = field.value.trim();
    status.textContent = "";
    if (!text) {
      box.dataset.state = "";
      status.innerHTML = hint;
      field.setCustomValidity("");
      return;
    }
    const found = recognise(text);
    if (found) {
      box.dataset.state = "ok";
      field.setCustomValidity("");
      const b = document.createElement("b");
      b.textContent = "✓ " + found.name + " link.";
      const open = document.createElement("a");
      open.href = found.href; open.target = "_blank"; open.rel = "noopener noreferrer";
      open.textContent = "Open it to check ↗";
      status.append(b, " Students get a button to it. ", open);
    } else {
      box.dataset.state = "bad";
      const msg = "That is not a link from a housing site we know. Use " + names + ".";
      field.setCustomValidity(msg);
      status.textContent = msg;
    }
  }

  field.addEventListener("input", update);
  field.addEventListener("paste", () => setTimeout(update, 0));
  update();
})();

// The photo gallery on an entry: the counter, the dots and the arrows follow
// whichever photo is in view, however it got there.
(function gallery() {
  const strip = document.querySelector("[data-gallery]");
  if (!strip) return;
  const hero = strip.closest(".hero");
  const at = hero.querySelector("[data-gallery-at]");
  const dots = Array.from(hero.querySelectorAll(".gallery-dots span"));
  const prev = hero.querySelector(".gallery-nav--prev");
  const next = hero.querySelector(".gallery-nav--next");
  const total = strip.children.length;

  function current() { return Math.round(strip.scrollLeft / strip.clientWidth); }
  function go(i) {
    i = Math.max(0, Math.min(total - 1, i));
    strip.scrollTo({ left: i * strip.clientWidth });
  }
  function show() {
    const i = current();
    if (at) at.textContent = i + 1;
    dots.forEach((d, n) => d.classList.toggle("on", n === i));
    if (prev) prev.hidden = i === 0;
    if (next) next.hidden = i === total - 1;
  }

  strip.addEventListener("scroll", () => window.requestAnimationFrame(show), { passive: true });
  if (prev) prev.addEventListener("click", () => go(current() - 1));
  if (next) next.addEventListener("click", () => go(current() + 1));
  strip.addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight") { e.preventDefault(); go(current() + 1); }
    if (e.key === "ArrowLeft") { e.preventDefault(); go(current() - 1); }
  });
  show();
})();

// Autofill on the housing form: from the link, or from the pasted advert.
// Whatever is found goes into the fields and lights up briefly, so the
// student sees what changed and checks it before publishing.
(function autofill() {
  const box = document.querySelector(".autofill");
  if (!box) return;
  const link = document.getElementById("external_url");
  const go = document.getElementById("autofill-go");
  const paste = document.getElementById("autofill-paste");
  const text = document.getElementById("autofill-text");
  const textGo = document.getElementById("autofill-text-go");
  const result = document.getElementById("autofill-result");
  const linkBox = box.querySelector(".linkfield");

  const NAMES = {
    title: "title", category: "kind of place", place: "area", price: "rent",
    bills_included: "bills", available_from: "move-in date",
    months_min: "minimum stay", address: "address", description: "description",
    features: "what the flat has",
  };
  const IDS = { bills_included: "bills" };

  function say(message, kind) {
    result.hidden = false;
    result.className = "autofill-result" + (kind ? " autofill-result--" + kind : "");
    result.textContent = message;
  }

  function mark(el) {
    if (!el) return;
    el.classList.remove("filled");
    void el.offsetWidth;            // restart the animation
    el.classList.add("filled");
  }

  function fill(fields) {
    const done = [];
    for (const [key, value] of Object.entries(fields)) {
      if (key === "features") {
        const boxes = Array.from(document.querySelectorAll('input[name="features"]'));
        let any = false;
        boxes.forEach((b) => {
          if (value.includes(b.value) && !b.checked) {
            b.checked = true; b.dispatchEvent(new Event("change", { bubbles: true }));
            mark(b.closest(".opt")); any = true;
          }
        });
        if (any) done.push(NAMES.features);
        continue;
      }
      const el = document.getElementById(IDS[key] || key);
      if (!el) continue;
      if (key === "description" && el.value.trim()) continue;  // never overwrite their words
      if (el.tagName === "SELECT" && !Array.from(el.options).some((o) => o.value === String(value))) continue;
      el.value = value;
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
      mark(el.closest(".prefixed") || el);
      if (NAMES[key]) done.push(NAMES[key]);
    }
    return done;
  }

  async function ask(body, button) {
    const label = button.textContent;
    button.disabled = true;
    button.textContent = "Reading the advert…";
    try {
      const res = await fetch("/new/autofill", { method: "POST", body });
      return await res.json();
    } catch (e) {
      return { ok: false, reason: "unreachable" };
    } finally {
      button.textContent = label;
      button.disabled = false;
      syncButton();
    }
  }

  function report(data) {
    const where = data.site ? " from " + data.site : "";
    if (data.ok) {
      const done = fill(data.fields || {});
      if (done.length) {
        say("Filled in" + where + ": " + done.join(", ") + ". Check it below and add what is missing.", "ok");
        return;
      }
    }
    if (data.reason === "blocked" || data.reason === "unreachable") {
      say((data.site || "That site") + " does not let apps read its adverts. No problem: open the advert, copy its text and paste it below.", "warn");
      paste.open = true;
      text.focus();
    } else if (data.reason === "site") {
      say("That link is not from a housing site we know.", "warn");
    } else {
      say("We could not find details in there. Fill in the form yourself, the link still goes on the entry.", "warn");
    }
  }

  function syncButton() {
    go.disabled = linkBox.dataset.state !== "ok";
  }
  link.addEventListener("input", syncButton);
  syncButton();

  go.addEventListener("click", async () => {
    const body = new FormData();
    body.append("url", link.value);
    report(await ask(body, go));
  });

  textGo.addEventListener("click", async () => {
    if (!text.value.trim()) { text.focus(); return; }
    const body = new FormData();
    body.append("text", text.value);
    const data = await ask(body, textGo);
    data.site = "the advert";
    report(data);
  });
})();
