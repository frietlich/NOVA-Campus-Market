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

// Which blocks you had open survives a trip into a chat, but not a trip out
// of the chats tab.
//
// Reading a chat and coming straight back should leave the list as you had
// it, even though that block is now settled and the server would fold it.
// Going to Tickets and back is a new visit, and then the list greets you the
// way it means to, with everything settled folded away.
(function keepFolds() {
  if (!location.pathname.startsWith("/chats")) return;
  const SHELF = "folds";

  const blocks = Array.from(document.querySelectorAll(".ch-block[data-key]"));
  if (!blocks.length) return;
  const boxOf = (block) => block.querySelector("input[type=checkbox]");

  const nearby = (where) => {
    if (!where) return false;
    try {
      const url = new URL(where);
      return url.origin === location.origin
        && (url.pathname.startsWith("/chats") || url.pathname.startsWith("/chat/"));
    } catch (err) {
      return false;
    }
  };

  const store = () => {
    const now = {};
    blocks.forEach((block) => {
      const box = boxOf(block);
      if (box) now[block.dataset.key] = box.checked;
    });
    try {
      sessionStorage.setItem(SHELF, JSON.stringify(now));
    } catch (err) {
      // A private window can refuse. Then every visit starts folded, which
      // is the server's answer anyway.
    }
  };

  if (nearby(document.referrer)) {
    let was = {};
    try {
      was = JSON.parse(sessionStorage.getItem(SHELF) || "{}");
    } catch (err) {
      was = {};
    }
    blocks.forEach((block) => {
      const box = boxOf(block);
      const before = was[block.dataset.key];
      if (box && typeof before === "boolean") box.checked = before;
    });
  } else {
    try {
      sessionStorage.removeItem(SHELF);
    } catch (err) {
      // Nothing to forget then.
    }
  }

  blocks.forEach((block) => {
    const box = boxOf(block);
    if (box) box.addEventListener("change", store);
  });
  window.addEventListener("pagehide", store);
})();

// Emptying the search box empties the search.
//
// The box is an ordinary form, so clearing it changes nothing until it is
// sent again. Pressing the little x in a search field looks like undoing the
// search, and then the old results sit there as though nothing happened.
// This only binds where a search is actually running, so typing something
// and changing your mind before sending it does not reload anything.
(function clearSearch() {
  document.querySelectorAll("form.search").forEach((form) => {
    const box = form.querySelector("input[type=search]");
    if (!box || !box.value.trim()) return;
    box.addEventListener("input", () => {
      if (box.value.trim() === "") form.submit();
    });
  });
})();

// The chat list comes back fresh, and at the height you left it.
//
// Two things fight here. A list has to be current, because a chat you have
// just read must not come back still marked unread, and that is why no page
// in this app may be kept by the browser. But a browser that keeps nothing
// also stops putting you back where you were, so the list writes its own
// place down before you leave.
(function keepPlace() {
  if (!location.pathname.startsWith("/chats")) return;
  const key = "place:" + location.pathname + location.search;
  const flag = key + ":back";

  const put = (name, value) => {
    try {
      sessionStorage.setItem(name, value);
    } catch (err) {
      // A private window can refuse to store. Then you land at the top,
      // which is a small loss and not worth breaking the page over.
    }
  };
  const take = (name) => {
    try {
      const value = sessionStorage.getItem(name);
      sessionStorage.removeItem(name);
      return value;
    } catch (err) {
      return null;
    }
  };

  const store = () => put(key, String(window.scrollY));
  window.addEventListener("pagehide", store);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) store();
  });

  // Belt and braces. no-store stops one browser from keeping the page, but
  // not every browser: some hand the living page straight back, and then the
  // dot you cleared is still sitting there. persisted says that happened, so
  // the page fetches itself, leaving a note to keep the place over the trip.
  window.addEventListener("pageshow", (event) => {
    if (!event.persisted) return;
    put(flag, "1");
    location.reload();
  });

  // Only on the way back. Opening the list fresh should start at the top.
  let back = Boolean(take(flag));
  if (!back) {
    try {
      const nav = performance.getEntriesByType("navigation")[0];
      back = Boolean(nav) && nav.type === "back_forward";
    } catch (err) {
      return;
    }
  }
  if (!back) return;

  const y = parseInt(take(key), 10);
  if (!y) return;
  // Once now and once after the first paint, because the drawn covers can
  // still be settling when this runs.
  window.scrollTo(0, y);
  requestAnimationFrame(() => window.scrollTo(0, y));
})();

// A back arrow goes back, not to a fixed address.
//
// The profile and a chat are both opened from whichever tab you were on, so
// their arrow has to return there. A plain link cannot know where you came
// from, and it cannot bring your scroll position with it either. When the
// page before this one was one of ours, the arrow therefore goes back
// through the browser instead of following its own address, which lands you
// exactly where you left. The address stays in the markup for the case where
// there is no page before this one, such as a link opened from outside.
(function backLinks() {
  const arrows = document.querySelectorAll("[data-back], .chat-head .icon-btn");
  if (!arrows.length || !document.referrer) return;
  let from;
  try {
    from = new URL(document.referrer);
  } catch (err) {
    return;
  }
  if (from.origin !== location.origin) return;
  if (from.pathname === location.pathname) return;
  arrows.forEach((arrow) => {
    arrow.addEventListener("click", (event) => {
      event.preventDefault();
      history.back();
    });
  });
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
