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
      say((data.site || "That site") + " does not let apps read its adverts. Fill in the form yourself, the link still goes on your entry.", "warn");
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
  const blocking = JSON.parse(linkBox.dataset.blocking || "[]");
  const goLabel = go.textContent;
  function blockedSite() {
    try {
      const v = link.value.trim();
      const host = new URL(v.includes("://") ? v : "https://" + v).hostname.toLowerCase();
      return blocking.find((d) => host === d || host.endsWith("." + d)) || null;
    } catch (e) { return null; }
  }
  function syncButton() {
    const ok = linkBox.dataset.state === "ok";
    const blocked = ok && blockedSite();
    go.disabled = !ok || Boolean(blocked);
    go.textContent = blocked ? "No autofill from this site, the link still goes on your entry" : goLabel;
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
// Two parts. First a short illustrated welcome, three cards you swipe through,
// where Bea, a (made-up) Nova student, says what the app is and how it works.
// Then, if you want, she points at the real buttons one by one.
// Shown once per browser. "Take the tour again" on the profile, or ?tour=1 in
// the address, plays it again. Skippable everywhere, Esc closes it.
(function tour() {
  const bar = document.querySelector(".tabbar");
  if (!bar) return;
  const asked = new URLSearchParams(location.search).get("tour") === "1";
  let seen = false;
  try { seen = localStorage.getItem("cm-tour-done") === "1"; } catch (e) {}
  if (seen && !asked) return;

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
    find: '<circle cx="11" cy="11" r="6.6"/><path d="M16.2 16.2 20.5 20.5"/>',
    chat: '<path d="M20.2 11.6c0 3.5-3.7 6.4-8.2 6.4-.9 0-1.8-.1-2.7-.4L5.3 19.3l1.1-3A6.1 6.1 0 0 1 3.8 11.6c0-3.5 3.7-6.4 8.2-6.4s8.2 2.9 8.2 6.4z"/>',
    done: '<circle cx="12" cy="12" r="8.6"/><path d="M8.4 12.3 11 14.8l4.6-5"/>',
  };
  const svg = (k, s = 22) => `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICON[k]}</svg>`;

  const CARDS = [
    { cls: "onb-hello", html: `
      <div class="onb-stage">${BEA(true)}<span class="onb-bubble">Olá! I'm Bea 👋</span></div>
      <h2>Welcome to Campus Market</h2>
      <p>I'm a Finance student, and I'll show you around. This is where Nova students
         offer each other rooms, tickets, things and spots in group projects.</p>
      <div class="onb-swap">
        <span class="onb-old"><b>40 WhatsApp groups</b><br><small>messages scroll away</small></span>
        <span class="onb-arrow">→</span>
        <span class="onb-new">1 app<br><small>entries stay until they are taken</small></span>
      </div>
      <p class="onb-small">Only students with a verified novasbe.pt address get in.</p>` },
    { cls: "onb-inside", html: `
      <div class="onb-stage onb-stage--small">${BEA(false)}<span class="onb-bubble onb-bubble--small">Pick a tab!</span></div>
      <h2>What's inside</h2>
      <p>Four tabs, each with its own colour.</p>
      <div class="onb-kinds">
        <div data-kind="housing">${svg("housing")}<b>Housing</b><span>Rooms, studios, flats. Link your Idealista or Uniplaces ad.</span></div>
        <div data-kind="ticket">${svg("ticket")}<b>Tickets</b><span>Parties, concerts, games, sorted by day.</span></div>
        <div data-kind="item">${svg("item")}<b>Market</b><span>Bikes, desks, books, anything you sell.</span></div>
        <div data-kind="group">${svg("group")}<b>Groups</b><span>A free spot in a project group, for your courses.</span></div>
      </div>` },
    { cls: "onb-how", html: `
      <div class="onb-stage onb-stage--small">${BEA(false)}</div>
      <h2>How it works</h2>
      <ol class="onb-steps">
        <li><span class="n" data-kind="housing">${svg("find", 20)}</span><div><b>Find it, or put it up</b><span>Search a tab, or tap + to offer something in a minute.</span></div></li>
        <li><span class="n" data-kind="ticket">${svg("chat", 20)}</span><div><b>Message the owner</b><span>You see how many asked before you:</span>
          <span class="onb-queue"><i></i><i></i><i class="me"></i><em>You are 3rd in line</em></span></div></li>
        <li><span class="n" data-kind="group">${svg("done", 20)}</span><div><b>Done, it disappears</b><span>The owner closes the entry and everyone sees it is taken.</span></div></li>
      </ol>` },
  ];

  const SPOTS = [
    { el: ".tabbar", title: "The four tabs", text: "Switch between Housing, Tickets, Market, Groups and your Chats down here." },
    { el: ".search", title: "Search and filters", text: "Look for anything in the tab you are in. Housing also filters by rent, area and minutes to campus." },
    { el: ".plus", title: "Put something up", text: "Tap + to offer something. For a room, paste its link and we fill in part of the form." },
    { el: ".card", title: "Open an entry", text: "Photos, the real monthly cost, the queue, and a button to message the owner." },
    { el: '.tab[href="/chats"]', title: "Your chats", text: "Everything you are talking about, by entry. That's it, have fun!" },
  ].filter((s) => document.querySelector(s.el));

  const root = document.createElement("div");
  root.className = "onb";
  root.setAttribute("role", "dialog");
  root.setAttribute("aria-modal", "true");
  root.setAttribute("aria-label", "Welcome tour");
  document.body.append(root);
  document.documentElement.classList.add("onb-open");

  function done() {
    try { localStorage.setItem("cm-tour-done", "1"); } catch (e) {}
    root.remove();
    document.documentElement.classList.remove("onb-open");
    document.removeEventListener("keydown", keys);
    window.removeEventListener("resize", onResize);
    if (asked) {
      const u = new URL(location.href); u.searchParams.delete("tour");
      history.replaceState(null, "", u.pathname + u.search);
    }
  }

  // ---- part 1: the welcome cards
  let c = 0, mode = "cards", s = 0;
  function cards() {
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
          <button type="button" class="onb-next">${last ? "Show me around" : "Next"}</button>
        </div>
        ${last ? '<button type="button" class="onb-later">No thanks, I\'ll explore myself</button>' : ""}
      </div>`;
    root.querySelector(".onb-skip").onclick = done;
    root.querySelector(".onb-next").onclick = () => (last ? spots() : (c++, cards()));
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

  // ---- part 2: Bea points at the real buttons
  function spots() {
    if (!SPOTS.length) return done();
    mode = "spots";
    root.className = "onb onb--spots";
    root.innerHTML = `<div class="onb-dim"></div><div class="onb-hole"></div><div class="onb-tip"></div>`;
    spot();
  }

  function spot() {
    const t = SPOTS[s];
    const el = document.querySelector(t.el);
    el.scrollIntoView({ block: "center", behavior: "instant" });
    const last = s === SPOTS.length - 1;
    const tip = root.querySelector(".onb-tip");
    tip.innerHTML = `
      <div class="onb-tip-top">${BEA_FACE}<div><b>${t.title}</b><p>${t.text}</p></div></div>
      <div class="onb-foot">
        <span class="onb-dots">${SPOTS.map((_, n) => `<i class="${n === s ? "on" : ""}"></i>`).join("")}</span>
        ${last ? "" : '<button type="button" class="onb-back onb-end">Skip</button>'}
        <button type="button" class="onb-next">${last ? "Let's go" : "Next"}</button>
      </div>`;
    tip.querySelector(".onb-next").onclick = () => (last ? done() : (s++, spot()));
    const end = tip.querySelector(".onb-end");
    if (end) end.onclick = done;
    place();
    tip.querySelector(".onb-next").focus();
  }

  function place() {
    if (mode !== "spots") return;
    const el = document.querySelector(SPOTS[s].el);
    const r = el.getBoundingClientRect(), pad = 6;
    const x = r.left - pad, y = r.top - pad, w = r.width + pad * 2, h = r.height + pad * 2;
    const rad = Math.min(18, h / 2), W = window.innerWidth, H = window.innerHeight;
    // The dark layer with a rounded hole cut out where the button is.
    root.querySelector(".onb-dim").style.clipPath = `path(evenodd, "M0 0H${W}V${H}H0Z ` +
      `M${x + rad} ${y}H${x + w - rad}A${rad} ${rad} 0 0 1 ${x + w} ${y + rad}V${y + h - rad}` +
      `A${rad} ${rad} 0 0 1 ${x + w - rad} ${y + h}H${x + rad}A${rad} ${rad} 0 0 1 ${x} ${y + h - rad}` +
      `V${y + rad}A${rad} ${rad} 0 0 1 ${x + rad} ${y}Z")`;
    Object.assign(root.querySelector(".onb-hole").style, {
      top: y + "px", left: x + "px", width: w + "px", height: h + "px", borderRadius: rad + "px",
    });
    const tip = root.querySelector(".onb-tip");
    const up = r.top + r.height / 2 > window.innerHeight / 2;
    tip.classList.toggle("onb-tip--up", up);
    tip.style.top = up ? "" : r.bottom + 18 + "px";
    tip.style.bottom = up ? window.innerHeight - r.top + 18 + "px" : "";
    const cx = Math.min(Math.max(r.left + r.width / 2, 40), window.innerWidth - 40);
    tip.style.setProperty("--arrow-x", cx - tip.getBoundingClientRect().left + "px");
  }

  function onResize() { place(); }
  function keys(e) {
    if (e.key === "Escape") return done();
    if (mode === "cards") {
      if (e.key === "ArrowRight" && c < CARDS.length - 1) { c++; cards(); }
      if (e.key === "ArrowLeft" && c > 0) { c--; cards(); }
    }
  }
  document.addEventListener("keydown", keys);
  window.addEventListener("resize", onResize);
  cards();
})();
