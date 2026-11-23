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
  // Only what is marked as a way back. This used to take every icon button
  // in a chat header, which was fine while the back arrow was the only one
  // there. The archive button is one too, and it was being turned into a
  // history.back() before it could ever send its form.
  const arrows = document.querySelectorAll("[data-back]");
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

// A number box that lets you type a word is a box that lies about itself.
// The browser checks a number field only when the form is sent, and a plain
// one happily takes e, a plus and a minus because that is legal in maths
// notation. These two keep the wrong character out of the box in the first
// place, so nobody ever sees a field refuse what it just accepted.
//
// Everything is read off the markup. A money box says inputmode decimal and
// a counting box is a number field, so no template has to mark anything.
(function numberBoxes() {
  // A money amount. Digits, one separator, two places after it.
  function tidy(box) {
    const was = box.value;
    let now = was.replace(/[^0-9.,]/g, "");
    const first = now.search(/[.,]/);
    if (first !== -1) {
      now = now.slice(0, first + 1) + now.slice(first + 1).replace(/[.,]/g, "");
      now = now.slice(0, first + 3);
    }
    if (now === was) return;
    const at = Math.max(0, box.selectionStart - (was.length - now.length));
    box.value = now;
    try {
      box.setSelectionRange(at, at);
    } catch (err) {
      // a field that does not carry a cursor, nothing to put back
    }
  }

  document.querySelectorAll("input[inputmode='decimal']").forEach((box) => {
    box.addEventListener("input", () => tidy(box));
  });

  // A whole number. Digits and nothing else. These are text fields on
  // purpose, because a number field hands back an empty string while it
  // holds something like 12e, and what you cannot read you cannot clean.
  document.querySelectorAll("input[inputmode='numeric']").forEach((box) => {
    box.addEventListener("input", () => {
      const was = box.value;
      const now = was.replace(/[^0-9]/g, "");
      if (now === was) return;
      const at = Math.max(0, box.selectionStart - (was.length - now.length));
      box.value = now;
      try {
        box.setSelectionRange(at, at);
      } catch (err) {
        // nothing to put back
      }
    });
  });

  // A money box that still ends in a separator when you leave it is just
  // an unfinished number, so it loses the dangling comma.
  document.querySelectorAll("input[inputmode='decimal']").forEach((box) => {
    box.addEventListener("blur", () => {
      box.value = box.value.replace(/[.,]$/, "");
    });
  });
})();

// Bills included means there is nothing to estimate, so the box goes dead
// instead of a sentence underneath asking people to leave it alone. What a
// disabled field holds is never sent, so the server gets nothing either.
(function billsBox() {
  const picker = document.getElementById("bills");
  const field = document.getElementById("bills_estimate");
  const box = document.getElementById("bills_box");
  if (!picker || !field || !box) return;

  function sync() {
    const included = picker.value === "1";
    field.disabled = included;
    box.classList.toggle("prefixed--off", included);
    if (included) field.value = "";
  }

  picker.addEventListener("change", sync);
  sync();
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

// The form from somewhere else: a ticket from the link to the event or from
// screenshots, a place from screenshots of the advert. The server reads it
// and sends back what it found, and those fields are filled in and marked,
// so the student sees at a glance what came from where and checks it.
(function autofill() {
  const box = document.getElementById("autofill");
  if (!box) return;
  const kind = box.dataset.kind;
  const most = Number(box.dataset.max) || 4;
  const input = document.getElementById("autofill_url");
  const go = document.getElementById("autofill-go");
  const shot = document.getElementById("autofill_shot");
  const shotLabel = document.getElementById("autofill-shot-label");
  const status = document.getElementById("autofill-status");
  const form = box.closest("form");
  const start = status.textContent.replace(/\s+/g, " ").trim();

  // Two notes, so a message has to pick one. What the link did belongs
  // under the link, what a screenshot did belongs under the screenshot
  // button. They shared one line at the foot until now, which is why
  // pressing Fill in on an empty field wiped the note that explains what
  // a screenshot is. The link note only exists on a ticket.
  const linkNote = document.getElementById("link-status");
  let note = status;

  const say = (text, how) => {
    note.textContent = text;
    note.classList.toggle("is-ok", how === "ok");
    note.classList.toggle("is-bad", how === "bad");
  };

  const REASONS = {
    site: "That link is not from a ticket site we know. Try Luma, DICE, Xceed, BOL or Eventbrite.",
    blocked: "{site} does not let apps read its pages. Take a screenshot instead, or type it in.",
    unreachable: "{site} did not answer. Check the link, or type it in.",
    empty: kind === "housing"
      ? "We found no housing advert in that. Please type it in."
      : "We found no event in that. Please type it in.",
    login: "Log in again, then try once more.",
    setup: "Screenshots are not switched on yet. Please type it in.",
    picture: "That file is not a screenshot we can read. Use a PNG or JPEG.",
    many: `At most ${most} screenshots at once.`,
    limit: "That is all the screenshots for today. Please type it in.",
    claude: "Claude could not read it just now. Try again in a minute, or type it in.",
  };
  const NAMES = { title: "title", category: kind === "housing" ? "kind of place" : "category",
                  event_date: "date", event_time: "time",
                  place: kind === "housing" ? "area" : "venue", address: "address",
                  price: kind === "housing" ? "rent" : "price",
                  bills_included: "bills", bills_estimate: "bills estimate",
                  deposit_months: "deposit", available_from: "free from",
                  months_min: "minimum stay", flatmates: "flatmates",
                  features: "features", description: "description" };

  // What the last fill put in. The next one first takes back whatever is
  // still untouched, so nothing from the wrong event or flat is left behind.
  let lastFilled = [];
  const mark = (field, target) => {
    target.classList.add("is-filled");
    const clear = () => target.classList.remove("is-filled");
    field.addEventListener("input", clear, { once: true });
    field.addEventListener("change", clear, { once: true });
  };
  const takeBack = () => {
    lastFilled.forEach(({ field, hint, target, before }) => {
      if (!target.classList.contains("is-filled")) return;
      if (field.type === "checkbox") {
        field.checked = false;
      } else {
        if (hint && !hint.parentNode) field.insertBefore(hint, field.firstChild);
        field.value = before;
        if (hint) field.selectedIndex = 0;
      }
      target.classList.remove("is-filled");
    });
    lastFilled = [];
  };

  const fill = (fields) => {
    takeBack();
    const done = [];
    Object.entries(fields).forEach(([name, value]) => {
      if (Array.isArray(value)) {
        // A row of tick boxes, like what a flat comes with.
        let any = false;
        value.forEach((one) => {
          const box = form.querySelector(`input[type="checkbox"][name="${name}"][value="${one}"]`);
          if (!box || box.checked) return;
          box.checked = true;
          const target = box.closest(".opt") || box;
          mark(box, target);
          lastFilled.push({ field: box, target });
          any = true;
        });
        if (any) done.push(NAMES[name] || name);
        return;
      }
      const field = form.querySelector(`[name="${name}"]`);
      if (!field || value === null) return;
      const before = field.value;
      if (field.tagName === "SELECT") {
        const option = field.querySelector(`option[value="${value}"]`);
        if (!option) return;
        const hint = field.querySelector("option[data-hint]");
        if (hint) hint.remove();
        field.value = value;
        lastFilled.push({ field, hint, target: field, before: "" });
      } else {
        if (value === "") return;
        field.value = String(value);
        lastFilled.push({ field, hint: null, target: field, before });
      }
      mark(field, field);
      done.push(NAMES[name] || name);
    });
    return done;
  };

  // One answer, from a link or from screenshots, goes into the form the same way.
  const show = (data) => {
    if (!data.ok) {
      say((REASONS[data.reason] || REASONS.empty).replace("{site}", data.site || "That site"), "bad");
      return;
    }
    const done = fill(data.fields || {});
    let text = `Filled in from ${data.site}: ${done.join(", ")}.`;
    if (kind === "ticket" && "price" in (data.fields || {})) {
      text += " The price is what the ticket cost there, change it to yours.";
    }
    say(text + " Check it before publishing.", "ok");
  };

  if (shot) {
    shot.addEventListener("change", async () => {
      note = status;
      const files = [...shot.files];
      if (!files.length) return;
      if (files.length > most) { say(REASONS.many, "bad"); shot.value = ""; return; }
      shotLabel.classList.add("is-busy");
      say(files.length === 1 ? "Claude is reading your screenshot…"
                             : `Claude is reading your ${files.length} screenshots…`);
      try {
        const body = new FormData();
        body.append("kind", kind);
        files.forEach((file) => body.append("screenshots", file));
        const res = await fetch("/new/screenshot", { method: "POST", body });
        show(await res.json());
      } catch (e) {
        say("Something went wrong. Please type it in.", "bad");
      } finally {
        shot.value = "";
        shotLabel.classList.remove("is-busy");
      }
    });
  }

  if (!input) return;
  const run = async () => {
    note = linkNote || status;
    const url = input.value.trim();
    if (!url) { say("Paste the link to the event first.", "bad"); input.focus(); return; }
    go.disabled = true;
    say("Reading the event page…");
    try {
      const body = new URLSearchParams({ url });
      const res = await fetch("/new/ticket-autofill", { method: "POST", body });
      show(await res.json());
    } catch (e) {
      say("Something went wrong. Please type it in.", "bad");
    } finally {
      go.disabled = false;
    }
  };

  // Dead until there is a link worth sending, the rule the housing form
  // already follows. The check that watches the field works out whether it
  // knows the site and writes the answer into data-state, so watching that
  // attribute is both the simplest way to ask and the only one that does
  // not depend on which of the two listeners the browser runs first.
  const field = input.closest(".linkfield");
  if (field) {
    const sync = () => {
      go.disabled = field.dataset.state !== "ok" || field.dataset.shut === "1";
    };
    new MutationObserver(sync).observe(field,
      { attributes: true, attributeFilter: ["data-state", "data-shut"] });
    sync();
  }

  go.addEventListener("click", run);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); run(); }
  });
  // Emptying the field puts the note back. Where there is a link note the
  // check that watches the field has already done it, with its own words.
  input.addEventListener("input", () => {
    if (input.value || linkNote) return;
    note = status;
    say(start);
  });
})();

// Push notifications. The browser is only asked after a tap, never on its
// own, and the device is then handed to the server, which sends to it.
(function notifications() {
  const meta = document.querySelector('meta[name="push-key"]');
  if (!meta) return;
  const key = meta.content;
  const supported = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
  const standalone = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone;
  const iphone = /iPhone|iPad|iPod/.test(navigator.userAgent);

  const bytes = (base64) => {
    const padded = (base64 + "=".repeat((4 - (base64.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/");
    return Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
  };

  const tell = (subscription) => fetch("/push/device", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(subscription.toJSON()),
  });

  // Gives back "on", "denied" or "unsupported".
  const enable = async () => {
    if (!supported) return "unsupported";
    const answer = await Notification.requestPermission();
    if (answer !== "granted") return "denied";
    const registration = await navigator.serviceWorker.register("/sw.js");
    await navigator.serviceWorker.ready;
    const subscription = (await registration.pushManager.getSubscription())
      || await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: bytes(key) });
    await tell(subscription);
    return "on";
  };

  // A device that said yes before is handed over again on every visit, so it
  // stays with whoever is logged in and survives a new address from the browser.
  if (supported && Notification.permission === "granted") {
    navigator.serviceWorker.register("/sw.js")
      .then((registration) => registration.pushManager.getSubscription())
      .then((subscription) => subscription && tell(subscription))
      .catch(() => {});
  }

  // The bell on a tab: turning it on first makes sure this device can hear it.
  document.querySelectorAll("form[data-push-ask]").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      if (form.dataset.asked || form.elements.on.value !== "1") return;
      event.preventDefault();
      form.dataset.asked = "1";
      try { await enable(); } catch (e) { /* the setting is still saved */ }
      form.submit();
    });
  });

  // The switches save the moment they move. The main switch greys out the
  // four below it, which keep their own position for when it comes back on.
  const all = document.getElementById("notify-all");
  if (all) {
    const form = all.closest("form");
    const areas = document.getElementById("notify-areas");
    form.querySelectorAll("input.switch").forEach((one) => {
      one.addEventListener("change", async () => {
        areas.classList.toggle("is-muted", !all.checked);
        try {
          await fetch(form.action, { method: "POST", body: new FormData(form) });
        } catch (e) {
          form.submit();
        }
      });
    });
  }

  // The settings page.
  const box = document.getElementById("push-device");
  if (!box) return;
  const status = document.getElementById("push-status");
  const on = document.getElementById("push-on");
  const test = document.getElementById("push-test");
  const ios = document.getElementById("push-ios");

  const showOn = () => {
    status.textContent = "On for this device.";
    on.hidden = true;
    test.hidden = false;
  };
  if (iphone && !standalone) ios.hidden = false;
  if (!supported) {
    on.hidden = true;
    if (!iphone) status.textContent = "This browser cannot do notifications.";
  } else if (Notification.permission === "granted") {
    navigator.serviceWorker.getRegistration("/")
      .then((registration) => registration && registration.pushManager.getSubscription())
      .then((subscription) => { if (subscription) showOn(); })
      .catch(() => {});
  } else if (Notification.permission === "denied") {
    // No second chance. A browser that has been told no never asks again,
    // so the button below could only ever do nothing. It goes, and the
    // line says where the answer can be changed.
    on.hidden = true;
    status.textContent = "Blocked for this site in your browser settings.";
  }

  on.addEventListener("click", async () => {
    on.disabled = true;
    try {
      const result = await enable();
      if (result === "on") showOn();
      else if (result === "denied") {
        on.hidden = true;
        status.textContent = "Blocked for this site in your browser settings.";
      } else status.textContent = "This browser cannot do notifications.";
    } catch (e) {
      status.textContent = "That did not work. Try again in a moment.";
    } finally {
      on.disabled = false;
    }
  });

  test.addEventListener("click", async () => {
    test.disabled = true;
    try {
      const res = await fetch("/push/test", { method: "POST" });
      const data = await res.json();
      status.textContent = data.ok ? "Sent. It should show up in a few seconds."
                                   : "Nothing reached this device. Turn it on again.";
    } finally {
      test.disabled = false;
    }
  });
})();

// A maps link dropped into the address box.
//
// People do not type a street, they copy the place out of maps, and the
// address box takes the link rather than refusing a line that is plainly
// not an address.
//
// A link only sometimes spells the address out. Google writes whatever was
// searched for after /place/, so searching an address gives the address but
// tapping a bar gives "K Urban Beach Club", and the short link a phone makes
// when you press Share carries nothing at all. Those two go to the server,
// which can follow a short link and look a coordinate up. Reading it here
// first means a link that already says the address costs nobody a request.
(function mapsLinks() {
  const boxes = document.querySelectorAll("input#address");
  if (!boxes.length) return;

  const PIN = /^-?\d+(\.\d+)?\s*,\s*-?\d+(\.\d+)?$/;
  const HAS_NUMBER = /\d/;
  const WHY = {
    not_maps: "That is a link, but not to Google or Apple maps.",
    off_list: "That link leads off maps. Copy the address instead.",
    unreachable: "Maps did not answer. Try again in a moment.",
    no_point: "There is no place in that link. Open it in maps and copy "
            + "the address line under the name.",
    nothing_there: "Nothing with a street name at that spot. Type the "
                 + "address instead.",
    login: "Sign in again to use this.",
  };

  function mapsHost(url) {
    const host = url.hostname.toLowerCase().replace(/^www\./, "");
    return host === "maps.apple.com"
        // Apple's own short domain, a top level domain of its own rather
        // than anything under apple.com. This is what an iPhone shares.
        || host === "maps.apple"
        || host === "maps.google.com"
        || host === "maps.app.goo.gl"
        || host === "goo.gl"
        || /(^|\.)google\.[a-z]{2,3}(\.[a-z]{2})?$/.test(host);
  }

  function addressIn(url) {
    // What sits after /place/ is whatever was searched for, so it is only
    // an address when it carries a number. A name is the very thing this
    // is meant to keep out of the box.
    const place = url.pathname.match(/\/maps\/place\/([^/]+)/);
    if (place) {
      const found = decodeURIComponent(place[1].replace(/\+/g, " ")).trim();
      if (found && !found.startsWith("@") && !PIN.test(found) && HAS_NUMBER.test(found)) {
        return found;
      }
    }
    for (const key of ["address", "q", "daddr", "destination"]) {
      const value = (url.searchParams.get(key) || "").trim();
      if (value && !PIN.test(value) && HAS_NUMBER.test(value)) return value;
    }
    return null;
  }

  boxes.forEach((box) => {
    const note = box.parentNode.querySelector("[data-address-note]");
    const wasSaying = note ? note.textContent : "";
    let back;
    const say = (words, keep) => {
      if (!note) return;
      clearTimeout(back);
      note.textContent = words || wasSaying;
      if (words && !keep) back = setTimeout(() => { note.textContent = wasSaying; }, 7000);
    };
    const put = (address) => {
      box.value = address.slice(0, box.maxLength > 0 ? box.maxLength : 120);
      box.classList.add("is-filled");
      box.addEventListener("input", () => box.classList.remove("is-filled"),
                           { once: true });
      say("");
    };

    let asking = false;
    const read = async () => {
      const text = box.value.trim();
      // Not a link at all, so this is somebody typing. Anything the box
      // complained about a moment ago is about a line that is gone.
      if (!/^https?:\/\//i.test(text)) {
        say("");
        return;
      }
      let url;
      try {
        url = new URL(text);
      } catch (err) {
        return;
      }
      if (!mapsHost(url)) {
        say(WHY.not_maps);
        return;
      }
      const here = addressIn(url);
      if (here) {
        put(here);
        return;
      }
      if (asking) return;
      asking = true;
      say("Looking that up…", true);
      try {
        const body = new FormData();
        body.append("url", text);
        const res = await fetch("/new/address-from-link", { method: "POST", body });
        const data = await res.json();
        if (data.ok) put(data.address);
        else say(WHY[data.reason] || WHY.nothing_there);
      } catch (err) {
        say("That did not work. Try again in a moment.");
      } finally {
        asking = false;
      }
    };

    // After the paste, so the box already holds the link.
    box.addEventListener("paste", () => setTimeout(read, 0));
    box.addEventListener("change", read);
  });
})();

// The housing link on the new entry form. While you type it says which site
// it recognised, offers to open it so you can check it is the right place,
// and stops the form from going off with a link we would refuse anyway.
(function housingLink() {
  const box = document.querySelector(".linkfield");
  if (!box) return;
  const field = box.querySelector("input");
  // On a room the line sits inside the field's box; on a ticket it is the
  // shared status line further down, under the screenshot button.
  const status = box.querySelector(".linkfield-status")
    || document.querySelector(".linkfield-status");
  if (!status) return;
  const platforms = JSON.parse(box.dataset.platforms || "[]");
  const blocking = JSON.parse(box.dataset.blocking || "[]");
  const names = box.dataset.names || "";
  // "housing" used to be written into the message here, which the ticket
  // form then said about a ticket link.
  const what = box.dataset.what || "site";
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
        return { name, href: url.toString(),
                 shut: blocking.includes(domain) };
      }
    }
    return null;
  }

  function update() {
    const text = field.value.trim();
    status.textContent = "";
    if (!text) {
      box.dataset.state = "";
      delete box.dataset.shut;
      status.innerHTML = hint;
      field.setCustomValidity("");
      return;
    }
    const found = recognise(text);
    if (found) {
      box.dataset.state = "ok";
      // A good link, and the form will keep it. Whether anything can be
      // read off it is a separate question, and the answer rides along so
      // the Fill in button can ask it without working it out again.
      if (found.shut) { box.dataset.shut = "1"; } else { delete box.dataset.shut; }
      field.setCustomValidity("");
      const b = document.createElement("b");
      b.textContent = "✓ " + found.name + " link.";
      const open = document.createElement("a");
      open.href = found.href; open.target = "_blank"; open.rel = "noopener noreferrer";
      open.textContent = "Open it to check ↗";
      status.append(b, " Students get a button to it. ", open);
      // Some of the sites we recognise shut apps out altogether. The link
      // is still worth keeping, so the button stays alive and says what to
      // expect instead of going dead with no reason given.
      if (found.shut) {
        const warn = document.createElement("span");
        warn.className = "linkfield-shut";
        warn.textContent = found.name + " does not let apps read it, so there"
          + " is nothing to fill in from. Type it in, and the link still goes"
          + " on your entry.";
        status.append(" ", warn);
      }
    } else {
      box.dataset.state = "bad";
      delete box.dataset.shut;
      const msg = "That is not a link from a " + what + " we know. Use " + names + ".";
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
  const dots = Array.from(hero.querySelectorAll(".gallery-dots span"));
  const prev = hero.querySelector(".gallery-nav--prev");
  const next = hero.querySelector(".gallery-nav--next");
  const total = strip.children.length;

  // Where the strip is, and where it is on its way to. Two presses in a row
  // have to count twice, and reading the scroll position would still give
  // the old photo while the first one is gliding over.
  let want = 0, settle = null;
  function current() { return Math.round(strip.scrollLeft / strip.clientWidth); }
  function go(i) {
    want = Math.max(0, Math.min(total - 1, i));
    strip.scrollTo({ left: want * strip.clientWidth });
  }
  function show() {
    const i = current();
    dots.forEach((d, n) => d.classList.toggle("on", n === i));
    if (prev) prev.hidden = i === 0;
    if (next) next.hidden = i === total - 1;
  }

  strip.addEventListener("scroll", () => {
    window.requestAnimationFrame(show);
    // Once it has come to rest, wherever it rested is what we wanted.
    clearTimeout(settle);
    settle = setTimeout(() => { want = current(); }, 120);
  }, { passive: true });
  if (prev) prev.addEventListener("click", () => go(want - 1));
  if (next) next.addEventListener("click", () => go(want + 1));
  strip.addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight") { e.preventDefault(); go(want + 1); }
    if (e.key === "ArrowLeft") { e.preventDefault(); go(want - 1); }
  });
  show();

  // ---- the photo, full screen
  //
  // A cropped thumbnail is no way to judge a room, so tapping a photo puts
  // it on the whole screen, whole, and you move through the others there
  // the same way. Closing it puts you back on the photo you ended on, not
  // the one you started from, because that is the one you were looking at.
  const ARROW = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">'
    + '<path d="M14.5 5.5 8 12l6.5 6.5" stroke="currentColor" stroke-width="2"'
    + ' stroke-linecap="round" stroke-linejoin="round"/></svg>';
  const CROSS = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">'
    + '<path d="M6.5 6.5l11 11M17.5 6.5l-11 11" stroke="currentColor" stroke-width="2"'
    + ' stroke-linecap="round"/></svg>';

  const shots = Array.from(strip.querySelectorAll(".gallery-shot"));
  const sources = shots.map((b) => b.querySelector("img").src);
  let big = null, bigStrip = null, bigDots = [], bigPrev = null, bigNext = null, cameFrom = null;

  let bigWant = 0, bigSettle = null;
  function bigAt() { return Math.round(bigStrip.scrollLeft / bigStrip.clientWidth); }
  function bigGo(i, smooth = true) {
    bigWant = Math.max(0, Math.min(total - 1, i));
    bigStrip.scrollTo({ left: bigWant * bigStrip.clientWidth, behavior: smooth ? "smooth" : "instant" });
  }
  function bigShow() {
    const i = bigAt();
    bigDots.forEach((d, n) => d.classList.toggle("on", n === i));
    if (bigPrev) bigPrev.hidden = i === 0;
    if (bigNext) bigNext.hidden = i === total - 1;
  }

  function build() {
    big = document.createElement("div");
    big.className = "lightbox";
    big.setAttribute("role", "dialog");
    big.setAttribute("aria-modal", "true");
    big.setAttribute("aria-label", "Photos");
    const many = total > 1;
    big.innerHTML =
      '<button class="lightbox-shut" type="button" aria-label="Close">' + CROSS + "</button>"
      + '<div class="lightbox-strip">'
      + sources.map((src, n) =>
          '<div class="lightbox-slide"><img src="' + src + '" alt="Photo ' + (n + 1)
          + " of " + total + '" draggable="false"></div>').join("")
      + "</div>"
      + (many ? '<div class="lightbox-dots" aria-hidden="true">'
          + sources.map(() => "<span></span>").join("") + "</div>" : "")
      + (many ? '<button class="lightbox-nav lightbox-nav--prev" type="button" aria-label="Previous photo">'
          + ARROW + "</button>"
          + '<button class="lightbox-nav lightbox-nav--next" type="button" aria-label="Next photo">'
          + ARROW + "</button>" : "");
    document.body.append(big);

    bigStrip = big.querySelector(".lightbox-strip");
    bigDots = Array.from(big.querySelectorAll(".lightbox-dots span"));
    bigPrev = big.querySelector(".lightbox-nav--prev");
    bigNext = big.querySelector(".lightbox-nav--next");

    bigStrip.addEventListener("scroll", () => {
      window.requestAnimationFrame(bigShow);
      clearTimeout(bigSettle);
      bigSettle = setTimeout(() => { bigWant = bigAt(); }, 120);
    }, { passive: true });
    if (bigPrev) bigPrev.addEventListener("click", () => bigGo(bigWant - 1));
    if (bigNext) bigNext.addEventListener("click", () => bigGo(bigWant + 1));
    big.querySelector(".lightbox-shut").addEventListener("click", shut);
    // A tap beside the photo closes it, the way every photo viewer does.
    big.addEventListener("click", (e) => { if (e.target === big || e.target === bigStrip) shut(); });
  }

  function keys(e) {
    if (e.key === "Escape") { e.preventDefault(); shut(); }
    if (e.key === "ArrowRight") { e.preventDefault(); bigGo(bigWant + 1); }
    if (e.key === "ArrowLeft") { e.preventDefault(); bigGo(bigWant - 1); }
  }

  function open(i, from) {
    if (!big) build();
    cameFrom = from || null;
    big.classList.add("is-open");
    document.documentElement.classList.add("lightbox-open");
    bigGo(i, false);
    bigWant = i;
    bigShow();
    document.addEventListener("keydown", keys);
    big.querySelector(".lightbox-shut").focus();
  }

  function shut() {
    const i = bigWant;
    big.classList.remove("is-open");
    document.documentElement.classList.remove("lightbox-open");
    document.removeEventListener("keydown", keys);
    // Back to the photo you were on, on the page behind.
    go(i);
    (cameFrom || shots[i] || shots[0]).focus({ preventScroll: true });
  }

  shots.forEach((b, n) => b.addEventListener("click", () => open(n, b)));
})();

// Autofill on the housing form: from the link, or from the pasted advert.
// Whatever is found goes into the fields and lights up briefly, so the
// student sees what changed and checks it before publishing.
(function autofill() {
  const box = document.querySelector(".autofill");
  if (!box) return;
  const link = document.getElementById("external_url");
  const go = document.getElementById("autofill-go");

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
    result.className = "note autofill-status autofill-result"
      + (kind ? " autofill-result--" + kind : "");
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
    button.textContent = "Reading…";
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
    // The line under the field has already warned that a site like this
    // may give nothing. This one says what actually came back, which is a
    // different thing, so it must not repeat the warning word for word.
    if (data.reason === "blocked") {
      say("Nothing came back from " + (data.site || "that site")
          + ". Fill the form in yourself.", "warn");
    } else if (data.reason === "unreachable") {
      say((data.site || "That site") + " did not answer. Check the link, or"
          + " fill the form in yourself.", "warn");
    } else if (data.reason === "limit") {
      say("You have filled in from links a lot in the last hour. Try again later, or fill in the form yourself.", "warn");
    } else if (data.reason === "site") {
      say("That link is not from a housing site we know.", "warn");
    } else {
      say("We could not find details in there. Fill in the form yourself, the link still goes on the entry.", "warn");
    }
  }

  // Idealista and Imovirtual refuse apps, so their links never go to the
  // server: the button says so and the paste box opens instead.
  // Alive for anything we recognise, the sites that shut apps out
  // included. Idealista used to grey it out, which left somebody holding
  // a link and a dead button. Pressing it there comes back empty within a
  // moment, nothing is fetched and no daily allowance is spent, and the
  // line under the field has already said to expect as much. A button you
  // can press and learn from beats one that only sits there.
  function syncButton() {
    go.disabled = linkBox.dataset.state !== "ok" || linkBox.dataset.shut === "1";
  }
  link.addEventListener("input", syncButton);
  syncButton();

  go.addEventListener("click", async () => {
    const body = new FormData();
    body.append("url", link.value);
    report(await ask(body, go));
  });

})();

// ------------------------------------------------------------------ the tour
//
// Two parts. First the story: four cards you swipe through, where Bea, a
// (made-up) Nova student, says why the app exists and how it works. Then, if
// you want, a walk through the whole app: she takes you from Housing to
// Tickets, Market, Groups, Chats and your profile, and points at the real
// buttons on each page.
//
// The walk goes from page to page, so where you are in it is kept in
// sessionStorage ("cm-tour-walk") and every page picks it up again. A step
// whose button is not on the page (no bell when notifications are off, no
// entries in an empty tab) is simply left out.
//
// Shown once per browser. "Take the tour again" on the profile, or ?tour=1 in
// the address, plays it again. Skippable everywhere, Esc closes it.
(function tour() {
  const WALK = "cm-tour-walk";
  const store = {
    get(k, s = localStorage) { try { return s.getItem(k); } catch (e) { return null; } },
    set(k, v, s = localStorage) { try { s.setItem(k, v); } catch (e) {} },
    drop(k, s = localStorage) { try { s.removeItem(k); } catch (e) {} },
  };
  const walking = store.get(WALK, sessionStorage);
  const asked = new URLSearchParams(location.search).get("tour") === "1";
  const bar = document.querySelector(".tabbar");
  // It starts by itself only on the main screens. On a wide screen the rail
  // is on every page, the forms included, and nobody wants a tour over a
  // half-written entry.
  const MAIN = ["/housing", "/tickets", "/market", "/groups", "/chats", "/profile"];
  if (walking === null) {
    if (!bar || !MAIN.includes(location.pathname.replace(/\/+$/, ""))) return;
    if (store.get("cm-tour-done") === "1" && !asked) return;
  }

  // Bea. Drawn here, in the colours of the app, no photo and no logo.
  const BEA = (wave) => `
  <svg class="bea" viewBox="0 0 160 190" aria-hidden="true">
    <ellipse cx="80" cy="182" rx="44" ry="6" fill="#000" opacity=".08"/>
    <path d="M44 74c-8 26 2 52 16 60h40c14-8 24-34 16-60z" fill="#3B2A22"/>
    <path d="M30 190c0-36 22-56 50-56s50 20 50 56z" fill="#12998A"/>
    <path d="M58 136c6 10 14 14 22 14s16-4 22-14" fill="none" stroke="#0B6F64" stroke-width="5" stroke-linecap="round"/>
    <path d="M73 150v20M87 150v20" stroke="#FFFFFF" stroke-width="2.5" stroke-linecap="round"/>
    <path d="M40 150c-4 16-4 28-2 40" stroke="#E5492F" stroke-width="7" stroke-linecap="round" fill="none"/>
    <rect x="72" y="112" width="16" height="22" rx="7" fill="#E0A982"/>
    <circle cx="80" cy="88" r="31" fill="#F2C29B"/>
    <path d="M48 86c-2-26 16-40 34-38 20 1 32 16 30 38-6-12-16-18-30-18-14 0-26 6-34 18z" fill="#3B2A22"/>
    <path d="M100 58c10-6 22-2 24 8-8-2-14 0-20 4z" fill="#3B2A22"/>
    <circle cx="69" cy="91" r="9" fill="none" stroke="#2A2A33" stroke-width="2.6"/>
    <circle cx="91" cy="91" r="9" fill="none" stroke="#2A2A33" stroke-width="2.6"/>
    <path d="M78 91h4" stroke="#2A2A33" stroke-width="2.6"/>
    <circle cx="69" cy="92" r="2.8" fill="#2A2A33"/><circle cx="91" cy="92" r="2.8" fill="#2A2A33"/>
    <circle cx="62" cy="104" r="4" fill="#F28C78" opacity=".45"/><circle cx="98" cy="104" r="4" fill="#F28C78" opacity=".45"/>
    <path d="M72 106c4 5 12 5 16 0" fill="none" stroke="#8A3B2A" stroke-width="2.6" stroke-linecap="round"/>
    ${wave ? `<g class="bea-arm">
      <path d="M118 150c10-10 16-26 18-44" stroke="#12998A" stroke-width="15" stroke-linecap="round" fill="none"/>
      <circle cx="137" cy="100" r="9" fill="#F2C29B"/></g>`
    : `<path d="M118 150c8 8 10 20 10 40" stroke="#12998A" stroke-width="15" stroke-linecap="round" fill="none"/>`}
    <g transform="rotate(-10 52 168)"><rect x="38" y="150" width="26" height="40" rx="5" fill="#2A2A33"/>
      <rect x="41" y="154" width="20" height="30" rx="3" fill="#9FE3D8"/></g>
  </svg>`;
  const BEA_FACE = BEA(false).replace('viewBox="0 0 160 190"', 'viewBox="40 46 80 80"').replace('class="bea"', 'class="bea-face"');

  const ICON = {
    housing: '<path d="M3.6 10.7 12 4.3l8.4 6.4V19a1.4 1.4 0 0 1-1.4 1.4h-3.6v-5.9h-6.8v5.9H5a1.4 1.4 0 0 1-1.4-1.4z"/>',
    ticket: '<rect x="3" y="7" width="18" height="10" rx="2.4"/><path d="M14.6 7.6v1.8m0 2.7v1.8m0 2.7v.8"/>',
    item: '<path d="M5.4 8h13.2l1 11.4a1.2 1.2 0 0 1-1.2 1.3H5.6a1.2 1.2 0 0 1-1.2-1.3z"/><path d="M9 8a3 3 0 0 1 6 0"/>',
    group: '<circle cx="9.2" cy="8.4" r="3.1"/><path d="M3.4 19.6c0-2.9 2.6-5.2 5.8-5.2s5.8 2.3 5.8 5.2M16.1 6.2a2.8 2.8 0 0 1 0 5.6M17.6 19.6c0-2.1-.8-3.7-2.2-4.7"/>',
    chats: '<path d="M20.2 11.6c0 3.5-3.7 6.4-8.2 6.4-.9 0-1.8-.1-2.7-.4L5.3 19.3l1.1-3A6.1 6.1 0 0 1 3.8 11.6c0-3.5 3.7-6.4 8.2-6.4s8.2 2.9 8.2 6.4z"/>',
    me: '<circle cx="12" cy="8.6" r="3.8"/><path d="M4.6 20c0-3.9 3.3-6.6 7.4-6.6s7.4 2.7 7.4 6.6"/>',
    find: '<circle cx="11" cy="11" r="6.6"/><path d="M16.2 16.2 20.5 20.5"/>',
    done: '<circle cx="12" cy="12" r="8.6"/><path d="M8.4 12.3 11 14.8l4.6-5"/>',
    shield: '<path d="M12 3.4 5 6.2v5.2c0 4.4 3 7.9 7 9.2 4-1.3 7-4.8 7-9.2V6.2z"/><path d="m9 12 2.2 2.2L15.4 10"/>',
    pin: '<path d="M12 20.6s-6.4-5.6-6.4-10.8a6.4 6.4 0 0 1 12.8 0c0 5.2-6.4 10.8-6.4 10.8z"/><circle cx="12" cy="9.8" r="2.3"/>',
    fair: '<path d="M12 4v16M5 8h14M7.6 8 4.8 14a3 3 0 0 0 5.6 0zM16.4 8l-2.8 6a3 3 0 0 0 5.6 0z"/>',
  };
  const svg = (k, s = 22) => `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICON[k]}</svg>`;

  // ---------------------------------------------------------- part 1, the story
  const CARDS = [
    { cls: "onb-hello", html: `
      <div class="onb-stage">${BEA(true)}<span class="onb-bubble">Olá! I'm Bea 👋</span></div>
      <h2>Welcome to Campus Market</h2>
      <p>I study Finance at Nova, and I'll show you around. This is where Nova
         students find rooms, tickets, second-hand things and teammates, from each other.</p>
      <div class="onb-swap">
        <span class="onb-old"><b>40 WhatsApp groups</b><br><small>and it's gone in an hour</small></span>
        <span class="onb-arrow">→</span>
        <span class="onb-new">1 app<br><small>it stays until it's taken</small></span>
      </div>` },
    { cls: "onb-why", html: `
      <div class="onb-stage onb-stage--small">${BEA(false)}<span class="onb-bubble onb-bubble--small">Why bother?</span></div>
      <h2>Why Campus Market</h2>
      <ul class="onb-why-list">
        <li><span class="n" data-kind="housing">${svg("shield", 20)}</span><div><b>Only Nova students</b><span>Everyone signed up with a verified novasbe.pt address. No strangers, no fake landlords.</span></div></li>
        <li><span class="n" data-kind="ticket">${svg("pin", 20)}</span><div><b>Nothing gets buried</b><span>Search and filter instead of scrolling back through chats.</span></div></li>
        <li><span class="n" data-kind="item">${svg("fair", 20)}</span><div><b>Fair for everyone</b><span>You see how many students reached out before you, and a taken entry is closed for all.</span></div></li>
      </ul>` },
    { cls: "onb-inside", html: `
      <div class="onb-stage onb-stage--small">${BEA(false)}<span class="onb-bubble onb-bubble--small">Pick a tab!</span></div>
      <h2>Four tabs, four colours</h2>
      <div class="onb-kinds">
        <div data-kind="housing">${svg("housing")}<b>Housing</b><span>Rooms, studios and flats, linked to the real ad.</span></div>
        <div data-kind="ticket">${svg("ticket")}<b>Tickets</b><span>Parties, concerts, games. Sorted by day.</span></div>
        <div data-kind="item">${svg("item")}<b>Market</b><span>Bikes, desks, books, anything you sell.</span></div>
        <div data-kind="group">${svg("group")}<b>Groups</b><span>A free spot in a project group for your course.</span></div>
      </div>` },
    { cls: "onb-how", html: `
      <div class="onb-stage onb-stage--small">${BEA(false)}</div>
      <h2>How it works</h2>
      <ol class="onb-steps">
        <li><span class="n" data-kind="housing">${svg("find", 20)}</span><div><b>Find it, or put it up</b><span>Search a tab, or tap + and offer something in a minute.</span></div></li>
        <li><span class="n" data-kind="ticket">${svg("chats", 20)}</span><div><b>Message the student</b><span>Every entry shows who reached out before you:</span>
          <span class="onb-queue"><i></i><i></i><i class="me"></i><em>You'd be the 3rd to reach out</em></span></div></li>
        <li><span class="n" data-kind="group">${svg("done", 20)}</span><div><b>Deal done, entry closed</b><span>Everyone sees it's taken, nobody writes for nothing.</span></div></li>
      </ol>` },
  ];

  // ---------------------------------------------------------- part 2, the walk
  // el is a selector, or a function that returns the element(s) to light up.
  const section = (name) => () => {
    const head = [...document.querySelectorAll(".section")].find((s) => s.textContent.trim() === name);
    if (!head) return null;
    const next = head.nextElementSibling;
    return next ? [head, next] : [head];
  };
  const CHAPTERS = {
    housing: { label: "Housing", icon: "housing", page: "/housing" },
    ticket: { label: "Tickets", icon: "ticket", page: "/tickets" },
    item: { label: "Market", icon: "item", page: "/market" },
    group: { label: "Groups", icon: "group", page: "/groups" },
    chats: { label: "Chats", icon: "chats", page: "/chats" },
    me: { label: "Profile", icon: "me", page: "/profile" },
  };
  const STEPS = [
    { ch: "housing", el: ".tabbar", title: "Your home base",
      text: "Housing, Tickets, Market, Groups and your Chats. Each tab has its own colour, so you always know where you are." },
    { ch: "housing", el: ".search", title: "Search anything",
      text: "A street, an area like Carcavelos, or just “balcony”. Search works the same way in every tab." },
    { ch: "housing", el: ".hbar", title: "Filters that matter",
      text: "Rent, area, bills included, minutes to campus, move-in date. Then sort by rent or by who's free first." },
    { ch: "housing", el: ".bell", title: "Let the rooms come to you",
      text: "Set your filters, then tap the bell. When a new room fits your search, your phone tells you." },
    { ch: "housing", el: () => document.querySelector(".head-actions .plus:not(.bell)") || document.querySelector(".tab--rail"), title: "Renting out your room?",
      text: "Tap +. Paste the Uniplaces or Idealista link, or a few screenshots of the ad, and the form fills itself in." },
    { ch: "housing", el: ".card", title: "The full picture",
      text: "Open a room: photos, rent plus bills worked out, a button to the original ad, and how many students reached out before you." },
    { ch: "housing", el: ".dock", title: "Your chats, right beside you",
      text: "On a big screen your chats stay open here. Read a room on the left and talk to the person letting it on the right." },

    { ch: "ticket", el: ".chips", title: "Tickets for what you're into",
      text: "Parties, concerts, sports and more. Tickets are sorted by day, so tonight is on top." },
    { ch: "ticket", el: ".card", title: "Sold out? Not here.",
      text: "Open a ticket and tap its bell: you hear when someone puts up another one for the same event." },
    { ch: "ticket", el: () => document.querySelector(".head-actions .plus:not(.bell)") || document.querySelector(".tab--rail"), title: "Can't make it?",
      text: "Sell your ticket in seconds: paste the Luma, DICE or Eventbrite link, or a screenshot, and it's filled in." },

    { ch: "item", el: ".filters", title: "Second-hand, first class",
      text: "Bikes, desks, books, a winter coat. Filter by category, price and condition." },
    { ch: "item", el: ".card", title: "Like it? Heart it.",
      text: "Open anything and tap the heart. Everything you saved waits for you on your profile." },

    { ch: "group", el: ".segment", title: "Only your courses",
      text: "Groups shows the project groups in the courses you take. Switch to All courses to look further." },
    { ch: "group", el: () => document.querySelector(".card") || document.querySelector(".empty"), title: "Missing a teammate?",
      text: "A group with a free spot posts it here. Message them and the spot is yours. The bell on a group tells you about new ones in that course." },

    { ch: "chats", el: '.segment', title: "Buying and selling, apart",
      text: "“You asked” is what you want. “Your entries” is who wrote about your things. They never get mixed up." },
    { ch: "chats", el: () => document.querySelector(".ch-list") || document.querySelector(".empty"), title: "One chat per entry",
      text: "Every chat is about one entry, so you always know who asked about what. Deal done? Archive it." },

    { ch: "me", el: ".panel", title: "This is you",
      text: "The tick means a verified Nova student. Everyone you talk to here has one too." },
    { ch: "me", el: section("My entries"), title: "Your entries",
      text: "Everything you put up. When it's gone, close it, and everybody sees it's taken." },
    { ch: "me", el: section("Notifications"), title: "You decide what pings you",
      text: "Saved searches, events and courses, all in one place. Turn any of them off when you like." },
  ];
  const ORDER = Object.keys(CHAPTERS);
  const here = location.pathname.replace(/\/+$/, "") || "/";
  const onPage = (n) => CHAPTERS[STEPS[n].ch].page === here;
  const find = (n) => {
    const el = STEPS[n].el;
    let got = typeof el === "function" ? el() : document.querySelector(el);
    if (!got) return null;
    got = (Array.isArray(got) ? got : [got]).filter((e) => e && e.getClientRects().length);
    return got.length ? got : null;
  };

  const root = document.createElement("div");
  root.className = "onb";
  root.setAttribute("role", "dialog");
  root.setAttribute("aria-modal", "true");
  root.setAttribute("aria-label", "Welcome tour");

  function open() {
    if (!root.isConnected) document.body.append(root);
    document.documentElement.classList.add("onb-open");
  }
  function done() {
    store.set("cm-tour-done", "1");
    store.drop(WALK, sessionStorage);
    root.remove();
    document.documentElement.classList.remove("onb-open");
    document.removeEventListener("keydown", keys);
    window.removeEventListener("resize", place);
    if (asked) {
      const u = new URL(location.href); u.searchParams.delete("tour");
      history.replaceState(null, "", u.pathname + u.search);
    }
  }

  // ---- part 1
  let c = 0, mode = "cards", s = 0, dir = 1;
  function cards() {
    open();
    mode = "cards";
    const last = c === CARDS.length - 1;
    root.className = "onb";
    root.innerHTML = `
      <div class="onb-sheet">
        <button type="button" class="onb-skip">Skip</button>
        <div class="onb-track" style="--i:${c}">
          ${CARDS.map((k, n) => `<section class="onb-card ${k.cls}" ${n === c ? "" : 'aria-hidden="true"'}>${k.html}</section>`).join("")}
        </div>
        <div class="onb-foot">
          <span class="onb-dots">${CARDS.map((_, n) => `<i class="${n === c ? "on" : ""}"></i>`).join("")}</span>
          ${c > 0 ? '<button type="button" class="onb-back">Back</button>' : ""}
          <button type="button" class="onb-next">${last ? "Show me around · 2 min" : "Next"}</button>
        </div>
        ${last ? '<button type="button" class="onb-later">No thanks, I\'ll explore myself</button>' : ""}
      </div>`;
    root.querySelector(".onb-skip").onclick = done;
    root.querySelector(".onb-next").onclick = () => (last ? walk(0, 1) : (c++, cards()));
    const back = root.querySelector(".onb-back");
    if (back) back.onclick = () => { c--; cards(); };
    const later = root.querySelector(".onb-later");
    if (later) later.onclick = done;
    root.querySelector(".onb-next").focus();
    swipe(root.querySelector(".onb-track"));
  }

  function swipe(el) {
    let x0 = null;
    el.addEventListener("touchstart", (e) => { x0 = e.touches[0].clientX; }, { passive: true });
    el.addEventListener("touchend", (e) => {
      if (x0 === null) return;
      const dx = e.changedTouches[0].clientX - x0; x0 = null;
      if (dx < -50 && c < CARDS.length - 1) { c++; cards(); }
      if (dx > 50 && c > 0) { c--; cards(); }
    });
  }

  // ---- part 2
  // Go to step n, or the nearest one in direction d that can be shown. A step
  // on another page means going there first; that page carries on.
  function walk(n, d) {
    dir = d;
    while (n >= 0 && n < STEPS.length) {
      if (!onPage(n)) return travel(n, d);
      if (find(n)) { s = n; store.set(WALK, `${n}:${d}`, sessionStorage); return spot(); }
      n += d;
    }
    return n < 0 ? (c = CARDS.length - 1, store.drop(WALK, sessionStorage), cards()) : finale();
  }

  function travel(n, d) {
    store.set(WALK, `${n}:${d}`, sessionStorage);
    const ch = CHAPTERS[STEPS[n].ch];
    open();
    mode = "travel";
    root.className = "onb onb--travel";
    root.innerHTML = `<div class="onb-go" data-kind="${STEPS[n].ch}">${svg(ch.icon, 26)}<span>${ch.label}</span></div>`;
    setTimeout(() => location.assign(ch.page), 260);
  }

  function chapterBar(n) {
    const at = ORDER.indexOf(STEPS[n].ch);
    return `<div class="onb-chapters">${ORDER.map((k, i) =>
      `<span class="${i < at ? "past" : i === at ? "now" : ""}" data-kind="${k}" title="${CHAPTERS[k].label}">${svg(CHAPTERS[k].icon, 14)}</span>`).join("")}</div>`;
  }

  function spot() {
    open();
    mode = "spots";
    const t = STEPS[s];
    const fresh = !root.classList.contains("onb--spots");
    if (fresh) {
      root.className = "onb onb--spots";
      root.innerHTML = `<div class="onb-dim"></div><div class="onb-hole"></div><div class="onb-tip"></div>`;
    }
    const els = find(s);
    els[0].scrollIntoView({ block: "center", behavior: "instant" });
    root.dataset.kind = t.ch;
    const tip = root.querySelector(".onb-tip");
    tip.innerHTML = `
      ${chapterBar(s)}
      <div class="onb-tip-top">${BEA_FACE}<div><small class="onb-ch">${CHAPTERS[t.ch].label}</small><b>${t.title}</b><p>${t.text}</p></div></div>
      <div class="onb-foot">
        <button type="button" class="onb-back onb-end">End tour</button>
        <button type="button" class="onb-back onb-prev" aria-label="Previous">←</button>
        <button type="button" class="onb-next">Next</button>
      </div>`;
    tip.querySelector(".onb-next").onclick = () => walk(s + 1, 1);
    tip.querySelector(".onb-prev").onclick = () => walk(s - 1, -1);
    tip.querySelector(".onb-end").onclick = done;
    // A bubble that was just made appears where it belongs; only a bubble
    // already on screen glides to its next place.
    if (fresh) tip.style.transition = "none";
    place();
    if (fresh) requestAnimationFrame(() => { tip.style.transition = ""; });
    tip.querySelector(".onb-next").focus({ preventScroll: true });
  }

  function place() {
    if (mode !== "spots") return;
    const els = find(s);
    if (!els) return;
    const rs = els.map((e) => e.getBoundingClientRect());
    const r = {
      left: Math.min(...rs.map((q) => q.left)), top: Math.min(...rs.map((q) => q.top)),
      right: Math.max(...rs.map((q) => q.right)), bottom: Math.max(...rs.map((q) => q.bottom)),
    };
    r.width = r.right - r.left; r.height = r.bottom - r.top;
    const W = window.innerWidth, H = window.innerHeight, pad = 6;
    const x = Math.max(r.left - pad, 4), y = Math.max(r.top - pad, 4);
    const w = Math.min(r.width + pad * 2, W - x - 4), h = Math.min(r.height + pad * 2, H - y - 4);
    const rad = Math.min(18, h / 2);
    // The dark layer with a rounded hole cut out where the button is.
    root.querySelector(".onb-dim").style.clipPath = `path(evenodd, "M0 0H${W}V${H}H0Z ` +
      `M${x + rad} ${y}H${x + w - rad}A${rad} ${rad} 0 0 1 ${x + w} ${y + rad}V${y + h - rad}` +
      `A${rad} ${rad} 0 0 1 ${x + w - rad} ${y + h}H${x + rad}A${rad} ${rad} 0 0 1 ${x} ${y + h - rad}` +
      `V${y + rad}A${rad} ${rad} 0 0 1 ${x + rad} ${y}Z")`;
    Object.assign(root.querySelector(".onb-hole").style, {
      top: y + "px", left: x + "px", width: w + "px", height: h + "px", borderRadius: rad + "px",
    });
    const tip = root.querySelector(".onb-tip");
    // Below the spot when there is room for the bubble, otherwise above it.
    const room = H - (y + h) - 18;
    const up = room < tip.offsetHeight + 12 && y > H - (y + h);
    tip.classList.toggle("onb-tip--up", up);
    tip.style.top = up ? "" : Math.min(y + h + 16, H - tip.offsetHeight - 12) + "px";
    tip.style.bottom = up ? Math.max(H - y + 16, 12) + "px" : "";
    // Sideways the bubble follows what it points at, so on a wide screen it
    // does not sit in the middle while the button is in the rail on the left.
    // On a phone it is as wide as the screen and simply stays put.
    const cx = Math.min(Math.max(r.left + r.width / 2, 40), W - 40);
    const tw = tip.offsetWidth;
    const left = Math.min(Math.max(cx - tw / 2, 12), Math.max(W - tw - 12, 12));
    tip.style.left = left + "px";
    tip.style.setProperty("--arrow-x", Math.min(Math.max(cx - left, 22), tw - 22) + "px");
  }

  function finale() {
    open();
    mode = "end";
    store.drop(WALK, sessionStorage);
    store.set("cm-tour-done", "1");
    root.className = "onb onb--end";
    root.innerHTML = `
      <div class="onb-sheet">
        <div class="onb-confetti" aria-hidden="true">${"<i></i>".repeat(18)}</div>
        <section class="onb-card onb-hello">
          <div class="onb-stage">${BEA(true)}<span class="onb-bubble">You're all set! 🎉</span></div>
          <h2>Go get it</h2>
          <p>Your room, your ticket for Saturday, your last teammate: it's all one tap away.</p>
          <p class="onb-small">Want to see this again? It's on your profile, under “Take the tour again”.</p>
        </section>
        <div class="onb-foot onb-foot--one">
          <button type="button" class="onb-next">Start exploring</button>
        </div>
      </div>`;
    root.querySelector(".onb-next").onclick = () => { done(); if (here !== "/housing") location.assign("/housing"); };
    root.querySelector(".onb-next").focus();
  }

  function keys(e) {
    if (e.key === "Escape") return done();
    if (mode === "cards") {
      if (e.key === "ArrowRight" && c < CARDS.length - 1) { c++; cards(); }
      if (e.key === "ArrowLeft" && c > 0) { c--; cards(); }
    } else if (mode === "spots") {
      if (e.key === "ArrowRight") walk(s + 1, 1);
      if (e.key === "ArrowLeft") walk(s - 1, -1);
    }
  }
  document.addEventListener("keydown", keys);
  window.addEventListener("resize", place);

  if (walking !== null) {
    const [n, d] = walking.split(":").map(Number);
    if (Number.isInteger(n) && n >= 0 && n < STEPS.length && onPage(n)) return walk(n, d === -1 ? -1 : 1);
    // Mid-walk on a page the walk was not heading to (the back button, a
    // link): offer to carry on instead of pulling the student anywhere.
    if (Number.isInteger(n) && n >= 0 && n < STEPS.length) {
      const pill = document.createElement("div");
      pill.className = "onb-resume";
      pill.innerHTML = `${BEA_FACE}<button type="button" class="onb-resume-go">Continue the tour</button><button type="button" class="onb-resume-x" aria-label="End the tour">✕</button>`;
      document.body.append(pill);
      pill.querySelector(".onb-resume-go").onclick = () => { pill.remove(); travel(n, 1); };
      pill.querySelector(".onb-resume-x").onclick = () => { pill.remove(); store.drop(WALK, sessionStorage); store.set("cm-tour-done", "1"); };
      return;
    }
    store.drop(WALK, sessionStorage);
  }
  cards();
})();
