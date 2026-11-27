/* Translate Bench leaderboard and dashboard.
 *
 * Everything is computed here from window.TB_DATA (data.js), written by
 * translate_bench/export/site_data.py from results/v1/, results/ltb-v1/ and results/v1.1/. Scores of a
 * selection use the release's aggregation: in each direction the mean of the selected text types
 * (sentences and passages 50:50), then the mean over directions. Paired 95% intervals use the release's
 * paired document bootstrap (the same 2,000 document draws as `translate-bench verify`), computed in the
 * browser. The Overall score and the hard-cases pass rate are one published figure per system each
 * (all 18 directions; the hard-case items in the release's directions) and do not follow the filters.
 */
"use strict";
(function () {
  const D = window.TB_DATA;
  const app = document.getElementById("app");
  const tip = document.getElementById("tooltip");
  const REPO = "https://github.com/takechanman1228/translate-bench";
  const README = REPO + "#readme";
  const doc = (p) => `${REPO}/blob/main/${p}`;
  // "sizes" was a view of its own; it now opens the model-size section of Speed & memory ("tradeoffs").
  // "about" was a view too; it now sends the visitor to the repository README. "metrics" has no tab but
  // keeps its route for older links.
  const VIEWS = ["leaderboard", "languages", "tradeoffs", "compare", "metrics", "system"];
  const TITLES = { leaderboard: "", languages: "Languages", tradeoffs: "Speed & memory", compare: "Compare", metrics: "Metric agreement" };
  const TK = { sentence: "s", passage: "p" };
  // The text-type selection "overall" (sentences and passages 50:50) is shown as "Both types", so it is not read as
  // the Overall score.
  const TYPE_NAME = { overall: "Both types (50:50)", sentence: "Sentences", passage: "Passages" };
  const LANG = Object.fromEntries(D.languages.map((l) => [l.code, l.name]));
  LANG.en = "English";
  const SYS = D.systems;
  const BY = Object.fromEntries(SYS.map((s) => [s.id, s]));
  // The judge comes with per-cell counts, so it follows the filters like the scores.
  const J = D.judge;
  // A selection with fewer sampled items than this shows the judge with its n but does not rank or correlate it.
  const JUDGE_MIN = 30;
  const JUDGE_MAX = D.directions.length * 2 * J.per_cell;
  // The measuring machine as "Apple M6 with 32 GiB" (chip and memory only).
  const CHIP = D.machine.split(",")[0];
  const MEMORY = (D.machine.match(/\d+ GiB/) || [""])[0];
  const MACHINE = MEMORY ? `${CHIP} with ${MEMORY}` : CHIP;
  const MINUS = "−";
  const NARROW = () => window.matchMedia("(max-width: 640px)").matches;

  // ---------------------------------------------------------------------------------------------
  // DOM helpers

  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    setAttrs(el, attrs);
    for (const kid of kids.flat(Infinity)) {
      if (kid == null || kid === false) continue;
      el.append(kid instanceof Node ? kid : String(kid));
    }
    return el;
  }
  function sv(tag, attrs, text) {
    const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
    setAttrs(el, attrs);
    if (text != null) el.textContent = text;
    return el;
  }
  function setAttrs(el, attrs) {
    if (!attrs) return;
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === "class") el.setAttribute("class", v);
      else if (k === "text") el.textContent = v;
      else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : v);
    }
  }
  const mean = (a) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : null);
  const isNum = (x) => typeof x === "number" && Number.isFinite(x);
  const fx = (x, d) => (isNum(x) ? x.toFixed(d) : "—");
  const signed = (x, d = 4) => {
    if (!isNum(x)) return "—";
    const t = Math.abs(x).toFixed(d);
    return /^0\.?0*$/.test(t) ? t : (x < 0 ? MINUS : "+") + t;
  };
  const pct = (x, d = 0) => (isNum(x) ? (100 * x).toFixed(d) + "%" : "—");
  const gib = (bytes) => (isNum(bytes) ? bytes / 2 ** 30 : null);
  const plural = (n, one, many) => `${n} ${n === 1 ? one : many || one + "s"}`;
  const langOf = (d) => (d.startsWith("en-") ? d.slice(3) : d.slice(0, -3));
  const dirName = (d) => (d.startsWith("en-") ? `English → ${LANG[langOf(d)]}` : `${LANG[langOf(d)]} → English`);
  const dirShort = (d) => d.replace("-en", "→en").replace(/^en-/, "en→");
  const shortName = (sys) => sys.name.replace(" framework (on-device)", "")
    .replace("Apple Intelligence on-device model (Foundation Models, permissive guardrails)", "Apple FM (permissive)")
    .replace("Apple Intelligence on-device model (Foundation Models)", "Apple FM");

  // ---------------------------------------------------------------------------------------------
  // Developer marks
  //
  // Path data from Simple Icons 16.38.1 (https://simpleicons.org, CC0 1.0), drawn in currentColor on a
  // 24 × 24 grid. The marks are trademarks of their owners and are used only to identify who makes each
  // system; their use implies no endorsement. A model's own mark is used where Simple Icons has one
  // (Claude, Gemini, Hy, Qwen), otherwise the developer's. Simple Icons has no current mark for OpenAI
  // (removed in 16.0.0), Preferred Networks or EuroLLM: those systems get a neutral badge with the
  // developer's initial. `pad` shrinks a heavy or edge-to-edge mark so all of them look the same size.
  const MARKS = {
    openai: { pad: 0, d: "M22.2819 9.8211a5.9847 5.9847 0 0 0-.5157-4.9108 6.0462 6.0462 0 0 0-6.5098-2.9A6.0651 6.0651 0 0 0 4.9807 4.1818a5.9847 5.9847 0 0 0-3.9977 2.9 6.0462 6.0462 0 0 0 .7427 7.0966 5.98 5.98 0 0 0 .511 4.9107 6.051 6.051 0 0 0 6.5146 2.9001A5.9847 5.9847 0 0 0 13.2599 24a6.0557 6.0557 0 0 0 5.7718-4.2058 5.9894 5.9894 0 0 0 3.9977-2.9001 6.0557 6.0557 0 0 0-.7475-7.0729zm-9.022 12.6081a4.4755 4.4755 0 0 1-2.8764-1.0408l.1419-.0804 4.7783-2.7582a.7948.7948 0 0 0 .3927-.6813v-6.7369l2.02 1.1686a.071.071 0 0 1 .038.052v5.5826a4.504 4.504 0 0 1-4.4945 4.4944zm-9.6607-4.1254a4.4708 4.4708 0 0 1-.5346-3.0137l.142.0852 4.783 2.7582a.7712.7712 0 0 0 .7806 0l5.8428-3.3685v2.3324a.0804.0804 0 0 1-.0332.0615L9.74 19.9502a4.4992 4.4992 0 0 1-6.1408-1.6464zM2.3408 7.8956a4.485 4.485 0 0 1 2.3655-1.9728V11.6a.7664.7664 0 0 0 .3879.6765l5.8144 3.3543-2.0201 1.1685a.0757.0757 0 0 1-.071 0l-4.8303-2.7865A4.504 4.504 0 0 1 2.3408 7.872zm16.5963 3.8558L13.1038 8.364 15.1192 7.2a.0757.0757 0 0 1 .071 0l4.8303 2.7913a4.4944 4.4944 0 0 1-.6765 8.1042v-5.6772a.79.79 0 0 0-.407-.667zm2.0107-3.0231l-.142-.0852-4.7735-2.7818a.7759.7759 0 0 0-.7854 0L9.409 9.2297V6.8974a.0662.0662 0 0 1 .0284-.0615l4.8303-2.7866a4.4992 4.4992 0 0 1 6.6802 4.66zM8.3065 12.863l-2.02-1.1638a.0804.0804 0 0 1-.038-.0567V6.0742a4.4992 4.4992 0 0 1 7.3757-3.4537l-.142.0805L8.704 5.459a.7948.7948 0 0 0-.3927.6813zm1.0976-2.3654l2.602-1.4998 2.6069 1.4998v2.9994l-2.5974 1.4997-2.6067-1.4997Z" },
    claude: { pad: 0, d: "m4.7144 15.9555 4.7174-2.6471.079-.2307-.079-.1275h-.2307l-.7893-.0486-2.6956-.0729-2.3375-.0971-2.2646-.1214-.5707-.1215-.5343-.7042.0546-.3522.4797-.3218.686.0608 1.5179.1032 2.2767.1578 1.6514.0972 2.4468.255h.3886l.0546-.1579-.1336-.0971-.1032-.0972L6.973 9.8356l-2.55-1.6879-1.3356-.9714-.7225-.4918-.3643-.4614-.1578-1.0078.6557-.7225.8803.0607.2246.0607.8925.686 1.9064 1.4754 2.4893 1.8336.3643.3035.1457-.1032.0182-.0728-.164-.2733-1.3539-2.4467-1.445-2.4893-.6435-1.032-.17-.6194c-.0607-.255-.1032-.4674-.1032-.7285L6.287.1335 6.6997 0l.9957.1336.419.3642.6192 1.4147 1.0018 2.2282 1.5543 3.0296.4553.8985.2429.8318.091.255h.1579v-.1457l.1275-1.706.2368-2.0947.2307-2.6957.0789-.7589.3764-.9107.7468-.4918.5828.2793.4797.686-.0668.4433-.2853 1.8517-.5586 2.9021-.3643 1.9429h.2125l.2429-.2429.9835-1.3053 1.6514-2.0643.7286-.8196.85-.9046.5464-.4311h1.0321l.759 1.1293-.34 1.1657-1.0625 1.3478-.8804 1.1414-1.2628 1.7-.7893 1.36.0729.1093.1882-.0183 2.8535-.607 1.5421-.2794 1.8396-.3157.8318.3886.091.3946-.3278.8075-1.967.4857-2.3072.4614-3.4364.8136-.0425.0304.0486.0607 1.5482.1457.6618.0364h1.621l3.0175.2247.7892.522.4736.6376-.079.4857-1.2142.6193-1.6393-.3886-3.825-.9107-1.3113-.3279h-.1822v.1093l1.0929 1.0686 2.0035 1.8092 2.5075 2.3314.1275.5768-.3218.4554-.34-.0486-2.2039-1.6575-.85-.7468-1.9246-1.621h-.1275v.17l.4432.6496 2.3436 3.5214.1214 1.0807-.17.3521-.6071.2125-.6679-.1214-1.3721-1.9246L14.38 17.959l-1.1414-1.9428-.1397.079-.674 7.2552-.3156.3703-.7286.2793-.6071-.4614-.3218-.7468.3218-1.4753.3886-1.9246.3157-1.53.2853-1.9004.17-.6314-.0121-.0425-.1397.0182-1.4328 1.9672-2.1796 2.9446-1.7243 1.8456-.4128.164-.7164-.3704.0667-.6618.4008-.5889 2.386-3.0357 1.4389-1.882.929-1.0868-.0062-.1579h-.0546l-6.3385 4.1164-1.1293.1457-.4857-.4554.0608-.7467.2307-.2429 1.9064-1.3114Z" },
    googlegemini: { pad: -0.8, d: "M11.04 19.32Q12 21.51 12 24q0-2.49.93-4.68.96-2.19 2.58-3.81t3.81-2.55Q21.51 12 24 12q-2.49 0-4.68-.93a12.3 12.3 0 0 1-3.81-2.58 12.3 12.3 0 0 1-2.58-3.81Q12 2.49 12 0q0 2.49-.96 4.68-.93 2.19-2.55 3.81a12.3 12.3 0 0 1-3.81 2.58Q2.49 12 0 12q2.49 0 4.68.96 2.19.93 3.81 2.55t2.55 3.81" },
    google: { pad: 1.4, d: "M12.48 10.92v3.28h7.84c-.24 1.84-.853 3.187-1.787 4.133-1.147 1.147-2.933 2.4-6.053 2.4-4.827 0-8.6-3.893-8.6-8.72s3.773-8.72 8.6-8.72c2.6 0 4.507 1.027 5.907 2.347l2.307-2.307C18.747 1.44 16.133 0 12.48 0 5.867 0 .307 5.387.307 12s5.56 12 12.173 12c3.573 0 6.267-1.173 8.373-3.36 2.16-2.16 2.84-5.213 2.84-7.667 0-.76-.053-1.467-.173-2.053H12.48z" },
    deepl: { pad: 1.1, d: "M20.907 4.93953 12.68543.18573a1.3577 1.3577 0 0 0-1.3709 0L3.09298 4.9565a1.3766 1.3766 0 0 0-.68639 1.18233v9.52646a1.3766 1.3766 0 0 0 .68639 1.19363l8.22157 4.75946.06223.03583 4.04856 2.3458-.01131-2.06106.0075-1.1446.0038.01885v-.38467c0-.23006.1188-.43371.29605-.56005l.264-.15086.12633-.06977h-.0075l4.80283-2.7795a1.3803 1.3803 0 0 0 .68639-1.19551V6.13505a1.3803 1.3803 0 0 0-.68642-1.19552m-9.85269 9.68863a1.4275 1.4275 0 0 1-.39976 1.3841 1.4086 1.4086 0 0 1-1.97054 0 1.4199 1.4199 0 0 1 0-2.06294 1.4086 1.4086 0 0 1 2.0422.07543l3.32822-1.91585.6864.38656zm5.77019-2.41367a1.4086 1.4086 0 0 1-1.97054 0 1.4256 1.4256 0 0 1-.3696-1.47837l-.0132.0075-3.7525-2.1723-.05657.05656a1.4086 1.4086 0 0 1-1.97053 0 1.4199 1.4199 0 0 1 0-2.06293 1.4086 1.4086 0 0 1 1.97242 0c.3941.37713.52422.91832.39033 1.40672l3.7808 2.20059.01886-.01886a1.4086 1.4086 0 0 1 1.97242 0 1.42746 1.42746 0 0 1 0 2.06105z" },
    tencenthy: { pad: 1, d: "M12 0a1 1 0 0 1 0 24 1 1 0 0 1 0-24m1.65 1.12c.533.097 1.023.233 1.41.404 6.086 2.686 7.398 9.217 1.603 14.341a3.782 3.782 0 0 1-6.126-1.75 3.66 3.66 0 0 1-.095-1.622c-1.934.6-3.295 2.305-3.524 4.45-.204 1.912.324 4.044 2.056 5.634A11 11 0 1 0 13.65 1.12M2.748 6.21A11 11 0 0 0 8.9 22.55c-5.377-4.022-6.06-8.4-2.43-13.87a2.234 2.234 0 1 0-3.722-2.47m10.157-5.172c4.408 1.33 3.61 5.41 2.447 6.924-.86 1.117-2.922 1.46-3.708 2.238a4.18 4.18 0 0 0-1.212 2.292A5.3 5.3 0 0 1 12 12.258a5.672 5.672 0 0 0 1.404-11.169 11 11 0 0 0-.5-.052" },
    qwen: { pad: 0.4, d: "M23.919 14.545 20.817 9.17l1.47-2.544a.56.56 0 0 0 0-.566l-1.633-2.83a.57.57 0 0 0-.49-.283h-6.207L12.487.402a.57.57 0 0 0-.49-.284H8.732a.56.56 0 0 0-.49.284L5.139 5.775h-2.94a.56.56 0 0 0-.49.284L.077 8.887a.56.56 0 0 0 0 .567L3.18 14.83l-1.47 2.545a.56.56 0 0 0 0 .566l1.634 2.83a.57.57 0 0 0 .49.283h6.205l1.47 2.545a.57.57 0 0 0 .49.284h3.266a.57.57 0 0 0 .49-.284l3.104-5.375h2.94a.57.57 0 0 0 .49-.283l1.634-2.828a.55.55 0 0 0-.004-.568M8.733.686l1.634 2.828-1.634 2.828H21.8L20.164 9.17H7.425L5.63 6.06Zm1.306 19.801-6.205-.002 1.634-2.83h3.265L2.201 6.344h3.267q3.182 5.517 6.367 11.032zm10.124-5.66L18.53 12l-6.532 11.315-1.634-2.83c2.129-3.673 4.25-7.351 6.373-11.028h3.592l3.102 5.374z" },
    bilibili: { pad: 0.9, d: "M17.813 4.653h.854c1.51.054 2.769.578 3.773 1.574 1.004.995 1.524 2.249 1.56 3.76v7.36c-.036 1.51-.556 2.769-1.56 3.773s-2.262 1.524-3.773 1.56H5.333c-1.51-.036-2.769-.556-3.773-1.56S.036 18.858 0 17.347v-7.36c.036-1.511.556-2.765 1.56-3.76 1.004-.996 2.262-1.52 3.773-1.574h.774l-1.174-1.12a1.234 1.234 0 0 1-.373-.906c0-.356.124-.658.373-.907l.027-.027c.267-.249.573-.373.92-.373.347 0 .653.124.92.373L9.653 4.44c.071.071.134.142.187.213h4.267a.836.836 0 0 1 .16-.213l2.853-2.747c.267-.249.573-.373.92-.373.347 0 .662.151.929.4.267.249.391.551.391.907 0 .355-.124.657-.373.906zM5.333 7.24c-.746.018-1.373.276-1.88.773-.506.498-.769 1.13-.786 1.894v7.52c.017.764.28 1.395.786 1.893.507.498 1.134.756 1.88.773h13.334c.746-.017 1.373-.275 1.88-.773.506-.498.769-1.129.786-1.893v-7.52c-.017-.765-.28-1.396-.786-1.894-.507-.497-1.134-.755-1.88-.773zM8 11.107c.373 0 .684.124.933.373.25.249.383.569.4.96v1.173c-.017.391-.15.711-.4.96-.249.25-.56.374-.933.374s-.684-.125-.933-.374c-.25-.249-.383-.569-.4-.96V12.44c0-.373.129-.689.386-.947.258-.257.574-.386.947-.386zm8 0c.373 0 .684.124.933.373.25.249.383.569.4.96v1.173c-.017.391-.15.711-.4.96-.249.25-.56.374-.933.374s-.684-.125-.933-.374c-.25-.249-.383-.569-.4-.96V12.44c.017-.391.15-.711.4-.96.249-.249.56-.373.933-.373Z" },
    bytedance: { pad: 1.4, d: "M19.8772 1.4685L24 2.5326v18.9426l-4.1228 1.0563V1.4685zm-13.3481 9.428l4.115 1.0641v8.9786l-4.115 1.0642v-11.107zM0 2.572l4.115 1.0642v16.7354L0 21.428V2.572zm17.4553 5.6205v11.107l-4.1228-1.0642V9.2568l4.1228-1.0642z" },
  };
  const MARK_RULES = [
    [(s) => /^Claude\b/.test(s.name), "claude"],
    [(s) => /^Gemini\b/.test(s.name), "googlegemini"],
    [(s) => s.developer === "OpenAI", "openai"],
    [(s) => /^Hy-MT/.test(s.family), "tencenthy"],
    [(s) => /^Qwen/.test(s.family), "qwen"],
    [(s) => s.developer === "Google", "google"],
    [(s) => s.developer === "DeepL", "deepl"],
    [(s) => s.developer === "Bilibili", "bilibili"],
    [(s) => s.developer === "ByteDance", "bytedance"],
  ];
  // The developer as shown. DeepL is only ever named as "DeepL API", so its system stands for it.
  const devName = (sys) => (sys.developer === "DeepL" ? sys.name : sys.developer);
  function devMark(sys) {
    const rule = MARK_RULES.find(([test]) => test(sys));
    const m = rule ? MARKS[rule[1]] : null;
    const name = devName(sys);
    // The initial comes from CSS (attr), so it is not part of the page's text when copied.
    if (!m) return h("span", { class: "mark-logo initial", role: "img", "aria-label": name, title: name, "data-initial": name.charAt(0).toUpperCase() });
    const svg = sv("svg", { class: "mark-logo", viewBox: `${-m.pad} ${-m.pad} ${24 + 2 * m.pad} ${24 + 2 * m.pad}`, role: "img", "aria-label": name, focusable: "false" });
    svg.append(sv("title", null, name), sv("path", { d: m.d }));
    return svg;
  }
  // A system's name with its mark; the Local/Cloud kind comes from the class.
  function markedName(sys, nameNode) {
    return h("span", { class: "named " + sys.kind }, devMark(sys), nameNode);
  }

  // ---------------------------------------------------------------------------------------------
  // State in the URL hash: #view?key=value&...

  const DEFAULT = {
    kind: "all", lang: "all", dir: "both", type: "overall", mem: "any", full: "0",
    sort: "overall", order: "", cols: "overall,comet,mx,judge,ef,hard,ss,mem", sys: "hy-mt2-30b-a3b,gpt-6.1-terra,deepl-api", metric: "comet",
    by: "pair", id: "",
  };
  // On a phone the default columns leave out MetricX-24 and the judge; the Columns menu still has them.
  const NARROW_COLS = "overall,comet,ef,hard,ss,mem";
  const colsShown = () => (st.cols === DEFAULT.cols && NARROW() ? NARROW_COLS : st.cols);
  // `full` hides the systems that do not cover every selected direction. Before v1.1 they were hidden unless
  // `partial=1`; that key is now ignored, since every system is shown by default.
  const FILTER_KEYS = ["kind", "lang", "dir", "type", "mem", "full"];
  let view = "leaderboard";
  let st = { ...DEFAULT };
  // A section to scroll to after the next render (from the old #sizes).
  let scrollTarget = null;

  // Reads the view and state from the hash; false when the hash sends the visitor elsewhere.
  function readHash() {
    const raw = decodeURIComponent(location.hash.slice(1));
    const [v, q] = raw.split("?");
    if (v === "about") { location.replace(README); return false; }
    view = v === "sizes" ? "tradeoffs" : VIEWS.includes(v) ? v : "leaderboard";
    st = { ...DEFAULT };
    const p = new URLSearchParams(q || "");
    for (const k of Object.keys(DEFAULT)) if (p.has(k)) st[k] = p.get(k);
    // Older links list the hidden columns instead of the shown ones.
    if (!p.has("cols") && p.has("hide")) {
      const hide = new Set(p.get("hide").split(","));
      st.cols = COLUMNS.filter((c) => !hide.has(c.key)).map((c) => c.key).join(",") || "none";
    }
    if (!["all", "local", "cloud"].includes(st.kind)) st.kind = "all";
    if (st.lang !== "all" && !LANG[st.lang]) st.lang = "all";
    if (!["both", "out", "into"].includes(st.dir)) st.dir = "both";
    if (!["overall", "sentence", "passage"].includes(st.type)) st.type = "overall";
    if (!["pair", "direction"].includes(st.by)) st.by = "pair";
    if (st.sort !== "name" && !COLUMNS.some((c) => c.key === st.sort)) st.sort = COLUMNS.some((c) => c.key === DEFAULT.sort) ? DEFAULT.sort : "comet";
    scrollTarget = v === "sizes" ? "sizes" : null;
    if (v === "sizes") history.replaceState(null, "", hashFor("tradeoffs"));
    return true;
  }
  function hashFor(v, changes) {
    const next = { ...st, ...(changes || {}) };
    const p = new URLSearchParams();
    for (const [k, val] of Object.entries(next)) if (val !== DEFAULT[k] && val !== "") p.set(k, val);
    const q = p.toString();
    return "#" + v + (q ? "?" + q : "");
  }
  function update(changes, push) {
    const target = hashFor(view, changes);
    if (push) location.hash = target;
    else {
      history.replaceState(null, "", target);
      readHash();
      render();
    }
  }

  // ---------------------------------------------------------------------------------------------
  // Selections and aggregation

  function scopeOf(s) {
    const dirs = D.directions.filter((d) => (s.lang === "all" || langOf(d) === s.lang)
      && (s.dir === "both" || (s.dir === "out") === d.startsWith("en-")));
    const types = s.type === "overall" ? ["s", "p"] : [TK[s.type]];
    return { dirs, types, key: dirs.join(",") + "|" + types.join("") };
  }
  function whereText(sc, s) {
    if (s.lang === "all") return s.dir === "both" ? `${D.directions.length} directions` : s.dir === "out" ? "9 directions from English" : "9 directions into English";
    if (s.dir === "both") return `English ↔ ${LANG[s.lang]} (2 directions)`;
    return dirName(sc.dirs[0]);
  }
  const scopeText = (sc, s) => `${TYPE_NAME[s.type]} · ${whereText(sc, s)}`;
  const cell = (sid, t, d) => (D.cells[sid] || {})[t + ":" + d];

  // Mean over the covered directions (those with every selected type) of the mean over the types.
  function measure(sid, sc, idx) {
    let sum = 0, n = 0;
    for (const d of sc.dirs) {
      let v = 0, ok = true;
      for (const t of sc.types) {
        const c = cell(sid, t, d);
        if (!c || c[idx] == null) { ok = false; break; }
        v += c[idx];
      }
      if (ok) { sum += v / sc.types.length; n++; }
    }
    return { value: n ? sum / n : null, n };
  }

  // Judge v1 over a selection, from per-cell counts (translate_bench/export/site_data.py aggregate_cells): each
  // counted direction weighs equally, its selected text types equally, the items of a cell equally; with both
  // types, only directions with items of both count. Pairwise cells are [wins, losses, judged ties, identical],
  // error cells [items with no error counted, items annotated].
  function judgeCells(cells, sc, stage) {
    if (!cells) return null;
    const used = sc.dirs.filter((d) => sc.types.every((t) => cells[t + ":" + d]));
    if (!used.length) return null;
    const share = 1 / (used.length * sc.types.length);
    let n = 0;
    if (stage === "errors") {
      let value = 0;
      for (const d of used) for (const t of sc.types) { const c = cells[t + ":" + d]; value += share * c[0] / c[1]; n += c[1]; }
      return { n, value, directions: used.length };
    }
    let w = 0, l = 0;
    const k = [0, 0, 0, 0];
    for (const d of used) for (const t of sc.types) {
      const c = cells[t + ":" + d], m = c[0] + c[1] + c[2] + c[3];
      w += share * c[0] / m; l += share * c[1] / m; n += m;
      c.forEach((x, i) => { k[i] += x; });
    }
    return { n, wins: k[0], losses: k[1], ties: k[2], identical: k[3], net: w - l, preferred: w + l > 0 ? w / (w + l) : null, directions: used.length };
  }
  const judgeEverywhere = (s) => s.lang === "all" && s.dir === "both";
  // Whether the judge is ranked and correlated on this selection: enough sampled items in it.
  const judgeRankable = (sc) => sc.dirs.length * sc.types.length * J.per_cell >= JUDGE_MIN;
  function judgeOf(sid, s) {
    const scopeName = s.type === "overall" ? "all" : s.type;
    const pub = (J.systems[sid] || {})[scopeName];
    const sc = scopeOf(s);
    const vs = judgeCells(J.pairwise[sid], sc, "pairwise"), ef = judgeCells(J.errors[sid], sc, "errors");
    // Over all 18 directions the published summary has the same values, with their bootstrap intervals.
    if (judgeEverywhere(s) && pub) {
      if (vs && pub.vs) vs.net95 = pub.vs.net95;
      if (ef && pub.ef) ef.ci = pub.ef.ci;
    }
    return { vs, ef };
  }

  function speedOf(sys, t) {
    if (sys.kind === "local") return sys.speed && sys.speed[t] ? { v: sys.speed[t].median, ref: false } : { v: null };
    const r = sys.reference && sys.reference[t];
    return r ? { v: r.seconds, ref: true } : { v: null };
  }

  function rowsFor(s) {
    const sc = scopeOf(s);
    return SYS.map((sys) => {
      const c = measure(sys.id, sc, 0);
      let scored = 0, attempted = 0;
      for (const d of sc.dirs) for (const t of sc.types) {
        const x = cell(sys.id, t, d);
        if (x) { scored += x[4]; attempted += x[6]; }
      }
      const j = judgeOf(sys.id, s);
      const ss = speedOf(sys, "s"), sp = speedOf(sys, "p");
      return {
        sys, id: sys.id, cover: c.n, total: sc.dirs.length, full: sc.dirs.length > 0 && c.n === sc.dirs.length,
        comet: c.value, mx: measure(sys.id, sc, 2).value, mxqe: measure(sys.id, sc, 3).value,
        chrf: measure(sys.id, sc, 1).value, done: attempted ? scored / attempted : null,
        judge: j.vs ? j.vs.preferred : null, judgeE: j.vs, ef: j.ef ? j.ef.value : null, efE: j.ef, ss: ss.v, ssRef: ss.ref, sp: sp.v, spRef: sp.ref,
        mem: sys.kind === "local" ? sys.memory : null, dl: gib(sys.download),
        hard: sys.ltb ? sys.ltb.rate : null, hardE: sys.ltb,
        overall: sys.overall && isNum(sys.overall.overall) ? sys.overall.overall : null, overallE: sys.overall,
      };
    });
  }

  function passes(r, s) {
    if (s.kind !== "all" && r.sys.kind !== s.kind) return false;
    if (s.mem !== "any" && (r.sys.kind !== "local" || !isNum(r.mem) || r.mem > +s.mem)) return false;
    // Over all directions every system is listed, also one without a complete direction (it has other figures).
    return r.cover > 0 || (s.lang === "all" && s.dir === "both");
  }

  // ---------------------------------------------------------------------------------------------
  // Paired document bootstrap (translate_bench/stats.py), on the items both systems scored

  const NDRAW = D.boot.m[0].length;
  const MULT = D.boot.m.map((str) => {
    const a = new Uint8Array(str.length);
    for (let i = 0; i < str.length; i++) a[i] = str.charCodeAt(i) - 48;
    return a;
  });
  const itemCache = new Map();
  function itemScores(sid, key) {
    const k = sid + "|" + key;
    if (!itemCache.has(k)) {
      const raw = (D.scores[sid] || {})[key];
      itemCache.set(k, raw == null ? null : Float64Array.from(raw.split(","), (x) => (x === "" ? NaN : +x / 1e6)));
    }
    return itemCache.get(k);
  }
  const cellPairCache = new Map();
  function cellPair(a, b, key) {
    const ck = a + "|" + b + "|" + key;
    if (cellPairCache.has(ck)) return cellPairCache.get(ck);
    const sa = itemScores(a, key), sb = itemScores(b, key);
    let out = null;
    if (sa && sb) {
      const docs = D.items.docs[key];
      const agg = new Map();
      let ps = 0, pn = 0;
      for (let i = 0; i < docs.length; i++) {
        const x = sa[i], y = sb[i];
        if (Number.isNaN(x) || Number.isNaN(y)) continue;
        let e = agg.get(docs[i]);
        if (!e) { e = [0, 0]; agg.set(docs[i], e); }
        e[0] += x - y; e[1] += 1; ps += x - y; pn++;
      }
      if (pn) {
        const num = new Float64Array(NDRAW), den = new Float64Array(NDRAW);
        for (const [d, [sum, n]] of agg) {
          const m = MULT[d];
          for (let k = 0; k < NDRAW; k++) {
            const w = m[k];
            if (w) { num[k] += w * sum; den[k] += w * n; }
          }
        }
        out = new Float64Array(NDRAW + 1);
        out[0] = ps / pn;
        for (let k = 0; k < NDRAW; k++) out[k + 1] = den[k] > 0 ? num[k] / den[k] : NaN;
        out.n = pn;
      }
    }
    cellPairCache.set(ck, out);
    return out;
  }
  function quantile(sorted, q) {
    const pos = (sorted.length - 1) * q, lo = Math.floor(pos), hi = Math.min(lo + 1, sorted.length - 1);
    return sorted[lo] + (pos - lo) * (sorted[hi] - sorted[lo]);
  }
  const pairCache = new Map();
  // COMET-22 of a minus b over the selection, with its paired 95% interval; null without common items.
  function paired(a, b, sc) {
    const key = sc.key + "|" + a + "|" + b;
    if (pairCache.has(key)) return pairCache.get(key);
    let result = null;
    if (a !== b && sc.dirs.length) {
      const acc = new Float64Array(NDRAW + 1);
      let ok = true, n = 0;
      for (const d of sc.dirs) {
        const parts = [];
        for (const t of sc.types) {
          const v = cellPair(a, b, t + ":" + d);
          if (!v) { ok = false; break; }
          parts.push(v); n += v.n;
        }
        if (!ok) break;
        for (let k = 0; k <= NDRAW; k++) {
          let v = 0;
          for (const p of parts) v += p[k];
          acc[k] += v / parts.length;
        }
      }
      if (ok) {
        const vals = [];
        for (let k = 0; k <= NDRAW; k++) acc[k] /= sc.dirs.length;
        for (let k = 1; k <= NDRAW; k++) if (Number.isFinite(acc[k])) vals.push(acc[k]);
        vals.sort((x, y) => x - y);
        if (Number.isFinite(acc[0]) && vals.length) {
          result = { delta: acc[0], lo: quantile(vals, 0.025), hi: quantile(vals, 0.975), n };
        }
      }
    }
    pairCache.set(key, result);
    return result;
  }
  const tied = (p) => p && p.lo <= 0 && p.hi >= 0;
  const ciText = (p) => (p ? `[${signed(p.lo)}, ${signed(p.hi)}]` : "");
  window.TB_PAIRED = (a, b, lang, dir, type) => paired(a, b, scopeOf({ lang: lang || "all", dir: dir || "both", type: type || "overall" }));

  // Work through a list in small slices so the page stays responsive; a new render stops the work.
  let jobToken = 0;
  function inSlices(items, fn, done) {
    const token = jobToken;
    let i = 0;
    function step() {
      if (token !== jobToken) return;
      const end = performance.now() + 24;
      while (i < items.length && performance.now() < end) fn(items[i++]);
      if (i < items.length) setTimeout(step, 0);
      else if (done) done();
    }
    setTimeout(step, 0);
  }

  // ---------------------------------------------------------------------------------------------
  // Tooltip

  // lines: a title line and detail lines, or one string shown as plain text (column help).
  function showTip(evt, lines) {
    if (typeof lines === "string") tip.replaceChildren(h("div", { class: "plain" }, lines));
    else tip.replaceChildren(...lines.filter(Boolean).map((l, i) => (i === 0 ? h("strong", null, l) : h("div", { class: i > 1 ? "muted" : null }, l))));
    tip.hidden = false;
    const r = evt.currentTarget && evt.currentTarget.getBoundingClientRect ? evt.currentTarget.getBoundingClientRect() : null;
    // From the keyboard there is no pointer position: align with the element's left edge, above it.
    const x = evt.clientX || (r ? r.left - 14 : 0), y = evt.clientY || (r ? r.top : 0);
    const w = tip.offsetWidth, hgt = tip.offsetHeight;
    tip.style.left = Math.max(8, Math.min(window.innerWidth - w - 8, x + 14)) + "px";
    tip.style.top = Math.max(8, y - hgt - 12 < 8 ? (r && !evt.clientY ? r.bottom + 8 : y + 16) : y - hgt - 12) + "px";
  }
  const hideTip = () => { tip.hidden = true; };
  // lines: as for showTip, or a function returning them when the tooltip opens (for values computed later).
  // A tooltip opens on hover of `el` and on keyboard focus of `focusEl` (by default `el` itself).
  function tipTarget(el, lines, focusEl) {
    const get = () => (typeof lines === "function" ? lines() : lines);
    const f = focusEl || el;
    el.addEventListener("pointerenter", (e) => showTip(e, get()));
    el.addEventListener("pointermove", (e) => showTip(e, get()));
    el.addEventListener("pointerleave", hideTip);
    f.addEventListener("focus", (e) => showTip(e, get()));
    f.addEventListener("blur", hideTip);
  }

  // ---------------------------------------------------------------------------------------------
  // Controls. data-k names a control so that focus returns to it after the view is drawn again.

  // A control's name is visible (`shown`, inside menus) or only announced (aria-label, in toolbars).
  function seg(label, key, options, shown) {
    const group = h("div", { class: "seg", role: "group", "aria-label": shown ? null : label, "aria-labelledby": shown ? "lbl-" + key : null },
      options.map(([value, text]) => h("button", {
        type: "button", "aria-pressed": String(st[key] === value), "data-k": `seg-${key}-${value}`,
        onclick: () => update({ [key]: value }),
      }, text)));
    return shown ? h("div", { class: "field" }, h("span", { class: "lbl", id: "lbl-" + key }, label), group) : group;
  }
  function select(label, key, options) {
    return h("select", { id: "f-" + key, "data-k": "sel-" + key, "aria-label": label, onchange: (e) => update({ [key]: e.target.value }) },
      options.map(([value, text]) => h("option", { value, selected: st[key] === value }, text)));
  }
  const langOptions = () => [["all", "All languages"], ...D.languages.map((l) => [l.code, l.name])];
  const kindSeg = () => seg("Systems", "kind", [["all", "All"], ["local", "Local"], ["cloud", "Cloud"]]);
  const langSelect = () => select("Language", "lang", langOptions());
  const dirSeg = (shown) => seg("Direction", "dir", [["both", "Both ways"], ["out", "From English"], ["into", "Into English"]], shown);
  const typeSeg = (shown) => seg("Text type", "type", [["overall", "Both types"], ["sentence", "Sentences"], ["passage", "Passages"]], shown);
  const memSelect = () => select("Peak memory", "mem", [["any", "Any memory"], ["4", "≤ 4 GiB"], ["8", "≤ 8 GiB"], ["16", "≤ 16 GiB"], ["24", "≤ 24 GiB"]]);
  function fullCheck(count) {
    return h("label", { class: "check" }, h("input", {
      type: "checkbox", checked: st.full === "1", "data-k": "chk-full", onchange: (e) => update({ full: e.target.checked ? "1" : "0" }),
    }), (st.lang === "all" && st.dir === "both" ? `Only systems with all ${D.directions.length} directions` : "Only systems with every selected direction")
      + (count != null ? ` (${count})` : ""));
  }
  let nextFocus = null;
  function resetButton(keys) {
    if (!keys.some((k) => st[k] !== DEFAULT[k])) return null;
    return h("button", {
      type: "button", class: "linkbtn", "data-k": "reset",
      onclick: () => { nextFocus = "seg-kind-all"; update(Object.fromEntries(keys.map((k) => [k, DEFAULT[k]]))); },
    }, "Reset");
  }
  // A toolbar of filters for the views other than the leaderboard; `resetKeys` adds keys that Reset
  // clears although their controls sit elsewhere on the view.
  function filters(opts, resetKeys) {
    const o = { kind: true, lang: true, mem: true, full: true, ...(opts || {}) };
    const parts = [];
    if (o.kind) parts.push(kindSeg());
    if (o.lang) parts.push(langSelect());
    parts.push(dirSeg());
    parts.push(typeSeg());
    if (o.mem) parts.push(memSelect());
    if (o.full) parts.push(fullCheck());
    const keys = FILTER_KEYS.filter((k) => (resetKeys || []).includes(k)
      || ((k !== "kind" || o.kind) && (k !== "lang" || o.lang) && (k !== "mem" || o.mem) && (k !== "full" || o.full)));
    const reset = resetButton(keys);
    return h("form", { class: "toolbar", "aria-label": "Filters", onsubmit: (e) => e.preventDefault() }, parts, reset ? h("div", { class: "tb-right" }, reset) : null);
  }
  // A disclosure that stays open while its controls redraw the view (render() notes which are open).
  const openMenus = new Set();
  function pop(name, summary, panel) {
    return h("details", { class: "pop", "data-menu": name, open: openMenus.has(name) },
      h("summary", { "data-k": "menu-" + name }, summary), h("div", { class: "menu" }, panel));
  }
  function kindCell(sys) {
    return h("span", { class: "kind " + sys.kind }, sys.kind === "local" ? "Local" : "Cloud");
  }
  function sysLink(sys) {
    return h("a", { href: hashFor("system", { id: sys.id }) }, sys.name);
  }
  function tableWrap(label, table) {
    return h("div", { class: "tablewrap", role: "region", "aria-label": label, tabindex: "0" }, table);
  }

  // ---------------------------------------------------------------------------------------------
  // Leaderboard

  // Overall (results/v1.1/) and Hard cases (results/ltb-v1/): one published figure per system, whatever the selection.
  const HAS_OVERALL = SYS.some((s) => s.overall && isNum(s.overall.overall));
  const HAS_HARD = SYS.some((s) => s.ltb);
  const HARD = D.hard_cases || { items: 0, verifier: "", benchmark: "Last Translation Benchmark" };
  // The fewest directions every pillar must cover for an Overall score (results/v1.1/overall.json).
  const MIN_DIRS = (D.overall_rule || {}).min_directions || D.directions.length;
  const COLUMNS = [
    ...(HAS_OVERALL ? [{ key: "overall", label: "Overall", better: "high" }] : []),
    { key: "comet", label: "COMET-22", better: "high" },
    { key: "delta", label: "Δ vs top", better: "high", sortKey: "comet" },
    { key: "mx", label: "MetricX-24", better: "low" },
    { key: "mxqe", label: "MetricX-24 QE", better: "low" },
    { key: "chrf", label: "chrF++", better: "high" },
    { key: "judge", label: "vs DeepL API", better: "high" },
    { key: "ef", label: "Error-free", better: "high" },
    ...(HAS_HARD ? [{ key: "hard", label: "Hard cases", better: "high" }] : []),
    { key: "done", label: "Completion", better: "high" },
    { key: "ss", label: "s / sentence", better: "low" },
    { key: "sp", label: "s / passage", better: "low" },
    { key: "mem", label: "Memory (GiB)", better: "low" },
    { key: "dl", label: "Download (GiB)", better: "low" },
    { key: "cover", label: "Directions", better: "high" },
    { key: "kind", label: "Kind", better: null, text: true },
    { key: "dev", label: "Developer", better: null, text: true },
  ];
  const BOARD_KEYS = [...FILTER_KEYS, "sort", "order", "cols"];
  function sortValue(r, key) {
    switch (key) {
      case "name": return r.sys.name.toLowerCase();
      case "kind": return r.sys.kind;
      case "dev": return devName(r.sys).toLowerCase();
      case "ss": return r.ssRef ? null : r.ss;
      case "sp": return r.spRef ? null : r.sp;
      default: return r[key];
    }
  }
  function sortRows(rows, key, order) {
    const col = COLUMNS.find((c) => c.key === key) || { better: "high" };
    const desc = order ? order === "desc" : col.better !== "low";
    const k = col.sortKey || key;
    const refRank = (r) => ((k === "ss" && r.ssRef) || (k === "sp" && r.spRef) ? 1 : 0);
    return rows.slice().sort((a, b) => {
      const va = sortValue(a, k), vb = sortValue(b, k);
      const na = va == null || (typeof va === "number" && !Number.isFinite(va)), nb = vb == null || (typeof vb === "number" && !Number.isFinite(vb));
      if (na !== nb) {
        const ra = refRank(a), rb = refRank(b);
        if (ra !== rb) return ra - rb;
        return na ? 1 : -1;
      }
      if (na && nb) {
        if (refRank(a) && refRank(b)) {
          const xa = k === "ss" ? a.ss : a.sp, xb = k === "ss" ? b.ss : b.sp;
          return desc ? xb - xa : xa - xb;
        }
        return (b.comet || 0) - (a.comet || 0);
      }
      if (va < vb) return desc ? 1 : -1;
      if (va > vb) return desc ? -1 : 1;
      return (b.comet || 0) - (a.comet || 0) || a.sys.name.localeCompare(b.sys.name);
    });
  }

  // Column help, shown as a tooltip on hover and on keyboard focus of the header.
  const REF = BY[J.reference].name;
  const COLUMN_HELP = {
    overall: `Mean of COMET-22 × 100, the error-free share (%) and the hard-case pass rate (%); a system below ${D.directions.length} directions (at least ${MIN_DIRS}) is scored over the directions it covers.`,
    comet: "Learned quality metric that compares the translation with a reference. Sentences and passages count 50:50; higher is better.",
    delta: "COMET-22 difference to the top COMET-22 system in this selection, with the paired 95% interval.",
    mx: "A second learned metric, as an error score from 0 to 25; lower is better.",
    mxqe: "MetricX-24 without the reference (quality estimation); lower is better.",
    chrf: "Character n-gram overlap with the reference; higher is better.",
    judge: `Share of non-tied items on which the LLM judge (${J.model_name}) preferred this system to ${REF}, on up to ${JUDGE_MAX} items.`,
    ef: `Share of items in which the LLM judge (${J.model_name}) marked no error, on up to ${JUDGE_MAX} items.`,
    hard: `Pass rate on ${HARD.items} hard items from the ${HARD.benchmark} in this benchmark's directions, verified by ${HARD.verifier}; below ${D.directions.length} directions, on the items in the directions a system covers.`,
    done: "Share of attempted items with a scored translation.",
    ss: `Median seconds per sentence on one ${MACHINE}, one request at a time. Cloud times are batched and shown only under Cloud.`,
    sp: `Median seconds per passage on one ${MACHINE}, one request at a time. Cloud times are batched and shown only under Cloud.`,
    mem: `Peak memory of the inference process on one ${MACHINE}.`,
    dl: "Size of the quantized weight file.",
    cover: "Directions with every selected text type, of those selected.",
  };
  const REF_DETAIL = "Batched client requests on Nov 20, including client start-up. In each direction the median of the items' seconds (a request's time divided by its items), then the mean over the directions measured";

  function boardToolbar(fullCount) {
    const active = (st.dir !== "both") + (st.type !== "overall") + (st.full === "1");
    const more = pop("filters",
      ["Filters", active ? h("span", { class: "badge" }, String(active), h("span", { class: "sr-only" }, " active")) : null],
      [dirSeg(true), typeSeg(true), fullCheck(fullCount)]);
    const cols = colsShown();
    const shown = new Set(cols === "none" ? [] : cols.split(","));
    const forced = COLUMNS.some((c) => c.key === st.sort) ? st.sort : null;
    const columns = pop("cols", "Columns", [
      h("div", { class: "colgrid" }, COLUMNS.map((c) => h("label", { class: "check" },
        h("input", {
          type: "checkbox", "data-k": "col-" + c.key, checked: shown.has(c.key) || c.key === forced, disabled: c.key === forced,
          title: c.key === forced ? "The table is sorted by this column" : null,
          onchange: (e) => {
            const next = new Set(shown);
            if (e.target.checked) next.add(c.key); else next.delete(c.key);
            update({ cols: COLUMNS.filter((x) => next.has(x.key)).map((x) => x.key).join(",") || "none" });
          },
        }), c.label))),
      h("button", { type: "button", class: "linkbtn", "data-k": "cols-reset", disabled: st.cols === DEFAULT.cols, onclick: () => update({ cols: DEFAULT.cols }) }, "Reset to default"),
    ]);
    return h("form", { class: "toolbar board-tools", "aria-label": "Filters", onsubmit: (e) => e.preventDefault() },
      kindSeg(), langSelect(), memSelect(),
      h("div", { class: "tb-right" }, more, columns, resetButton(BOARD_KEYS)));
  }

  // The Overall score with its three pillars, as tooltip lines; below 18 directions they are means over the
  // directions a system covers.
  const NDIR = D.directions.length;
  const langList = (codes) => codes.map((c) => LANG[c] || c).join(", ");
  function pillarText(e) {
    const part = (v, n, text) => (isNum(v) ? text + (n != null && n < NDIR ? ` (${n} of ${NDIR} directions)` : "") : null);
    return [part(e.standard, e.directions.standard, `COMET-22 × 100 ${fx(e.standard, 2)}`),
      part(e.reliability, e.directions.reliability, `error-free ${fx(e.reliability, 1)}%`),
      part(e.hard_cases, e.directions.hard_cases, `hard cases ${fx(e.hard_cases, 1)}%`)].filter(Boolean).join(" · ");
  }
  function noOverallReason(r) {
    const e = r.overallE;
    if (!e) return "no published figures";
    const d = e.directions;
    return `COMET-22 with both text types in ${d.standard} of ${NDIR} directions, the judge in ${d.reliability}; it needs ${MIN_DIRS} in every pillar`;
  }
  function overallTip(r) {
    const e = r.overallE;
    if (!e) return [r.sys.name, "No Overall score"];
    if (!isNum(e.overall)) return ["No Overall score", r.sys.name, noOverallReason(r), pillarText(e)];
    const cov = e.coverage < NDIR
      ? `The mean of the three over the ${e.coverage} of ${NDIR} directions it covers (no ${langList(e.missing_languages)})`
      : `The mean of the three, over all ${NDIR} directions`;
    return [`Overall ${fx(e.overall, 1)}`, r.sys.name, pillarText(e), `${cov}; it does not change with the filters`];
  }
  // Coverage of a row: of the selection when it misses a selected direction, else of the Overall score when that
  // covers fewer than 18 directions; null when complete.
  function coverageOf(r) {
    if (!r.full) return { n: r.cover, total: r.total, selection: true };
    if (r.overallE && r.overallE.coverage < NDIR) return { n: r.overallE.coverage, total: NDIR, selection: false };
    return null;
  }
  function coverageBadge(r) {
    const c = coverageOf(r);
    if (!c) return null;
    const e = r.overallE;
    const missing = e && e.missing_languages.length ? ` (no ${langList(e.missing_languages)})` : "";
    const lines = c.selection
      ? [`${c.n} of ${c.total} selected directions`, r.sys.name,
        c.n ? "Its scores here are means over the directions it covers, and it is not ranked on them." : "No direction of this selection with both text types.",
        e && isNum(e.overall) ? `Its Overall score is a mean over the ${e.coverage} of ${NDIR} directions it covers${missing}.` : null]
      : [`${c.n} of ${NDIR} directions`, r.sys.name, `Its Overall score is a mean over the directions it covers${missing}.`,
        "The other columns cover this selection in full."];
    const badge = h("span", { class: "cov", tabindex: "0", "aria-label": `${c.n} of ${c.total} directions` }, `${c.n}/${c.total}`);
    tipTarget(badge, lines);
    return badge;
  }

  // Four picks above the table: the top cloud and local systems, and the best local systems within 8 and
  // 4 GiB of peak memory, by the Overall score (COMET-22 without one).
  function boardTiles(rows) {
    const key = HAS_OVERALL ? "overall" : "comet";
    const full = rows.filter((r) => isNum(r[key]) && (HAS_OVERALL || r.full)).sort((a, b) => b[key] - a[key] || b.comet - a.comet);
    const local = full.filter((r) => r.sys.kind === "local");
    const within = (gib) => local.find((r) => isNum(r.mem) && r.mem <= gib);
    // Each figure stays on one line; a narrow tile wraps between them.
    const figs = (...xs) => xs.map((x, i) => [i ? h("span", { class: "dot" }, " · ") : null, h("span", { class: "fig" }, x)]);
    const score = (r) => (HAS_OVERALL ? `${fx(r.overall, 1)} overall` : `${fx(r.comet, 4)} COMET-22`);
    const scoreTip = (r) => [r.sys.name, ...(HAS_OVERALL ? [`Overall ${fx(r.overall, 1)}`, pillarText(r.overallE)] : [`COMET-22 ${fx(r.comet, 4)}`])];
    const localLine = (r) => figs(score(r), isNum(r.mem) ? fx(r.mem, 2) + " GiB" : "—", isNum(r.ss) ? fx(r.ss, 2) + " s" : "—");
    const localTip = (r) => [...scoreTip(r),
      `Peak memory ${isNum(r.mem) ? fx(r.mem, 2) + " GiB" : "not measured"} · ${isNum(r.ss) ? fx(r.ss, 2) + " s per sentence" : "speed not measured"}`];
    const picks = [
      ["Top cloud", full.find((r) => r.sys.kind === "cloud"), (r) => figs(score(r)), scoreTip],
      ["Top local", local[0], localLine, localTip],
      ["Best within 8 GiB", within(8), localLine, localTip],
      ["Best within 4 GiB", within(4), localLine, localTip],
    ];
    return h("div", { class: "tiles picks" }, picks.map(([label, r, line, tipLines]) => {
      if (!r) return h("div", { class: "tile" }, h("div", { class: "t-lbl" }, label), h("div", { class: "t-name" }, "—"));
      const a = h("a", { class: "tile", href: hashFor("system", { id: r.id }) },
        h("div", { class: "t-lbl" }, label), h("div", { class: "t-name" }, markedName(r.sys, [h("span", { class: "nm" }, r.sys.name), coverageBadge(r)])),
        h("div", { class: "t-sub num" }, line(r)));
      if (tipLines) tipTarget(a, tipLines(r));
      return a;
    }));
  }

  function viewLeaderboard() {
    const sc = scopeOf(st);
    const every = rowsFor(st);
    const all = every.filter((r) => passes(r, st));
    const ranked = all.filter((r) => r.full);
    const onlyFull = st.full === "1";
    const shown = onlyFull ? ranked : all;
    const judgeRank = judgeRankable(sc);
    const sortKey = !judgeRank && ["judge", "ef"].includes(st.sort) ? "comet" : st.sort;
    const rows = sortRows(shown, sortKey, st.order);
    const leader = ranked.slice().sort((a, b) => b.comet - a.comet)[0];
    const cloudOnly = st.kind === "cloud";
    // DeepL API is the baseline of the pairwise judge: no rank when the table is sorted by preference.
    const byPreference = sortKey === "judge";
    // Sorted by the Overall score, every system with one is ranked, also over fewer directions (with its badge);
    // one without comes last, unranked. Sorted by another column, a system missing a selected direction is
    // listed with its means over the covered directions, unranked.
    const unranked = (r) => (sortKey === "overall" ? !isNum(r.overall) : !r.full);
    // The shown columns, plus the one the table is sorted by.
    const colsNow = colsShown();
    const want = new Set(colsNow === "none" ? [] : colsNow.split(","));
    if (COLUMNS.some((c) => c.key === sortKey)) want.add(sortKey);
    let cols = COLUMNS.filter((c) => want.has(c.key));
    if (NARROW()) {
      // On a phone the sorted metric (or COMET-22) and the judge come first, next to the system names.
      const leadKey = COLUMNS.some((c) => c.key === sortKey && !c.text) ? sortKey : "comet";
      const first = cols.filter((c) => c.key === leadKey), second = cols.filter((c) => c.key === "judge" && c.key !== leadKey);
      cols = [...first, ...second, ...cols.filter((c) => !first.includes(c) && !second.includes(c))];
    }

    const out = [h("h1", { class: "sr-only" }, "Leaderboard"), boardToolbar(ranked.length)];
    // The picks above the table, for the whole field only (no kind or memory filter).
    if (st.kind === "all" && st.mem === "any") {
      out.push(boardTiles(onlyFull ? every.filter((r) => r.full && !(r.overallE && r.overallE.coverage < NDIR)) : every));
    }

    const sortCol = COLUMNS.find((c) => c.key === sortKey);
    const sortDesc = st.order ? st.order === "desc" : !sortCol || sortCol.better !== "low";
    function th(c) {
      const isSorted = c.key === sortKey;
      const label = (c.key === "ss" || c.key === "sp") && cloudOnly ? `${c.label} (batched)` : c.label;
      const arrow = c.better === "high" ? "↑" : c.better === "low" ? "↓" : "";
      const text = [label, arrow ? h("span", { class: "arr", "aria-hidden": "true" }, arrow) : null];
      const cls = [c.text ? null : "n", isSorted ? "sorted" : null].filter(Boolean).join(" ") || null;
      const help = COLUMN_HELP[c.key];
      if ((c.key === "judge" || c.key === "ef") && !judgeRank) {
        // Too few sampled items in this selection: shown, but neither ranked nor sortable.
        const cell = h("th", { scope: "col", class: cls, tabindex: "0" }, text);
        tipTarget(cell, `${help} Fewer than ${JUDGE_MIN} sampled items in this selection: not ranked.`);
        return cell;
      }
      const btn = h("button", {
        class: "sort", type: "button", "data-k": "sort-" + c.key,
        onclick: () => (isSorted ? update({ order: sortDesc ? "asc" : "desc" }) : update({ sort: c.key, order: "" })),
      }, text, isSorted ? h("span", { class: "caret", "aria-hidden": "true" }, sortDesc ? "▼" : "▲") : null);
      const cell = h("th", { scope: "col", class: cls, "aria-sort": isSorted ? (sortDesc ? "descending" : "ascending") : null }, btn);
      if (help) {
        btn.setAttribute("aria-description", help);
        tipTarget(cell, help, btn);
      }
      return cell;
    }
    const nameSorted = sortKey === "name";
    const thead = h("thead", null, h("tr", null,
      h("th", { scope: "col", class: "n rank" }, "#"),
      h("th", { scope: "col", class: "sys" + (nameSorted ? " sorted" : ""), "aria-sort": nameSorted ? (st.order === "desc" ? "descending" : "ascending") : null },
        h("button", { class: "sort", type: "button", "data-k": "sort-name", onclick: () => update({ sort: "name", order: nameSorted && st.order !== "desc" ? "desc" : "asc" }) },
          "System", nameSorted ? h("span", { class: "caret", "aria-hidden": "true" }, st.order === "desc" ? "▼" : "▲") : null)),
      cols.map(th)));

    // Paired intervals against the top system arrive after the table is drawn.
    const deltas = new Map(), marks = new Map(), deltaTds = new Map();
    const cometTip = (r) => {
      const lines = [`COMET-22 ${fx(r.comet, 4)}`, r.sys.name];
      if (!r.full) lines.push(`${r.cover} of ${r.total} directions covered; not ranked`);
      else if (leader && r.id === leader.id) lines.push("Top COMET-22 in this selection");
      else if (leader) {
        const p = deltas.get(r.id);
        if (p === undefined) lines.push("Δ vs the top COMET-22: computing…");
        else if (p) {
          lines.push(`Δ vs the top COMET-22 (${leader.sys.name}): ${signed(p.delta)}, 95% interval ${ciText(p)}`);
          if (tied(p)) lines.push("≈ tied with it: the paired 95% interval includes zero");
        }
      }
      return lines;
    };
    const star = () => null;  // the coverage badge next to the name marks a row's means over fewer directions
    function cellFor(r, c) {
      switch (c.key) {
        case "overall": {
          const td = h("td", { class: "n" + (isNum(r.overall) ? "" : " na"), tabindex: r.overallE ? "0" : null }, fx(r.overall, 1));
          if (r.overallE) tipTarget(td, overallTip(r));
          return td;
        }
        case "comet": {
          const mark = h("span", { class: "mark" }, "");
          marks.set(r.id, mark);
          const td = h("td", { class: "n" + (r.full ? "" : " partial"), tabindex: "0" }, mark, fx(r.comet, 4), star(r));
          tipTarget(td, () => cometTip(r));
          return td;
        }
        case "delta": {
          const td = h("td", { class: "n" }, r.full ? (leader && r.id === leader.id ? "top" : "…") : "—");
          if (r.full && !(leader && r.id === leader.id)) deltaTds.set(r.id, td);
          return td;
        }
        case "mx": case "mxqe": case "chrf": {
          const v = r[c.key];
          return h("td", { class: "n" + (r.full ? "" : " partial") }, fx(v, c.key === "chrf" ? 2 : 3), isNum(v) ? star(r) : null);
        }
        case "judge": {
          if (r.id === J.reference) return h("td", { class: "n na", title: "The baseline of the pairwise judge: every other system is compared with it" }, "baseline");
          if (!r.judgeE) return h("td", { class: "n na" }, "—");
          const e = r.judgeE;
          const td = h("td", { class: "n", tabindex: "0" }, pct(e.preferred));
          tipTarget(td, [`${pct(e.preferred)} of non-tied items preferred to ${BY[J.reference].name}`, r.sys.name,
            `${e.wins} wins, ${e.losses} losses, ${e.ties} judged ties` + (e.identical != null ? ` and ${e.identical} identical outputs` : "") + `: ${e.n} items` + (e.directions ? ` in ${e.directions} direction${e.directions > 1 ? "s" : ""}` : "") + " (ties and identical outputs are left out of the share)",
            e.net95 ? `net ${signed(e.net, 3)} [${signed(e.net95[0], 3)}, ${signed(e.net95[1], 3)}]` : `net ${signed(e.net, 3)}; intervals are shown over all 18 directions only`]);
          return td;
        }
        case "ef": {
          if (!r.efE) return h("td", { class: "n na" }, "—");
          const e = r.efE;
          const td = h("td", { class: "n", tabindex: "0" }, pct(e.value));
          tipTarget(td, [`${pct(e.value)} of items with no error counted`, r.sys.name,
            `n ${e.n}: ${e.n} items` + (e.directions ? ` in ${e.directions} direction${e.directions > 1 ? "s" : ""}` : "") + `, annotated by ${J.model_name}` + (e.ci ? `; 95% interval ${pct(e.ci[0])}–${pct(e.ci[1])}` : "; intervals are shown over all 18 directions only")]);
          return td;
        }
        case "hard": {
          if (!r.hardE) return h("td", { class: "n na" }, "—");
          const e = r.hardE;
          const td = h("td", { class: "n", tabindex: "0" }, pct(e.rate, 1));
          tipTarget(td, [`${pct(e.rate, 1)} of ${e.items} hard items passed (${e.passed})`, r.sys.name,
            `${HARD.benchmark} items in ${e.directions < NDIR ? `the ${e.directions} directions it covers` : "this benchmark's directions"}, verified by ${HARD.verifier}; 95% interval ${pct(e.ci[0], 1)}–${pct(e.ci[1], 1)}`,
            e.all ? `On all ${e.all.items} items: ${pct(e.all.rate, 1)} (${e.all.passed}); the items in the directions it does not cover leave the denominator` : null,
            "One figure per system; it does not change with the filters"]);
          return td;
        }
        case "done": return h("td", { class: "n" }, isNum(r.done) ? (r.done === 1 ? "100%" : pct(r.done, 1)) : "—");
        case "ss": case "sp": {
          const v = r[c.key], ref = c.key === "ss" ? r.ssRef : r.spRef;
          if (!isNum(v)) return h("td", { class: "n na" }, "—");
          if (!ref) return h("td", { class: "n" }, fx(v, 2));
          // Cloud times come from batched requests: shown only when the table lists cloud systems alone.
          const td = h("td", { class: "n" + (cloudOnly ? "" : " na"), tabindex: "0" }, cloudOnly ? fx(v, 2) : "—");
          tipTarget(td, [r.sys.name, `Cloud, batched requests: ${fx(v, 2)} s per ${c.key === "ss" ? "sentence" : "passage"} (not comparable with local times)`, REF_DETAIL]);
          return td;
        }
        case "mem": {
          if (r.sys.kind === "cloud") return h("td", { class: "n na" }, "—");
          if (!isNum(r.mem)) {
            const td = h("td", { class: "n na", tabindex: r.sys.memory_measured === false ? "0" : null }, "—");
            if (r.sys.memory_measured === false) tipTarget(td, [r.sys.name, "Runs in a system service; not measured"]);
            return td;
          }
          return h("td", { class: "n" }, fx(r.mem, 2));
        }
        case "dl": return h("td", { class: "n" + (isNum(r.dl) ? "" : " na") }, isNum(r.dl) ? fx(r.dl, 1) : "—");
        case "cover": return h("td", { class: "n" }, `${r.cover}/${r.total}`);
        case "kind": return h("td", null, kindCell(r.sys));
        case "dev": return h("td", null, devName(r.sys));
        default: return h("td", null, "");
      }
    }
    function sysCell(r) {
      const sys = r.sys;
      const short = shortName(sys);
      const name = short === sys.name ? sys.name : [h("span", { class: "wide-only" }, sys.name), h("span", { class: "narrow-only" }, short)];
      return h("td", { class: "sys" },
        markedName(sys, [h("a", { href: hashFor("system", { id: sys.id }) }, name),
          h("span", { class: "sr-only" }, sys.kind === "local" ? " (local)" : " (cloud)"), coverageBadge(r)]));
    }

    let rank = 0;
    const tbody = h("tbody", null, rows.length ? rows.map((r) => {
      const baseline = byPreference && r.id === J.reference;
      if (!unranked(r) && !baseline) rank++;
      const rankTitle = baseline ? "The baseline of the pairwise judge: not ranked by preference"
        : !unranked(r) ? null : sortKey === "overall" ? `No Overall score: ${noOverallReason(r)}`
          : "Not every selected direction covered: not ranked on this column";
      return h("tr", { class: "k-" + r.sys.kind + (r.full ? "" : " partial-row") },
        h("td", { class: "rank n", title: rankTitle }, baseline ? "baseline" : unranked(r) ? "—" : String(rank)),
        sysCell(r), cols.map((c) => cellFor(r, c)));
    }) : h("tr", null, h("td", { class: "na", colspan: String(cols.length + 2) }, "No systems match these filters.")));
    const caption = h("caption", { class: "sr-only" }, `Translate Bench v1.1 · ${scopeText(sc, st)}`);
    const busy = leader && ranked.length > 1;
    const table = h("table", { class: "board", "data-busy": busy ? "1" : null }, caption, thead, tbody);
    out.push(tableWrap("Leaderboard table", table));

    out.push(h("p", { class: "legend-line" },
      h("span", { class: "kbar local" }, "Local"), h("span", { class: "kbar cloud" }, "Cloud"),
      h("span", null, h("b", { class: "tie-mark", "aria-hidden": "true" }, "≈"), " tied with the top COMET-22"),
      rows.some((r) => coverageOf(r)) ? [h("span", { class: "sep", "aria-hidden": "true" }, "·"),
        h("span", null, h("span", { class: "cov", "aria-hidden": "true" }, `16/${NDIR}`), " means over the directions a system covers")] : null));

    if (busy) {
      // ≈ marks the systems whose paired COMET-22 interval against the top COMET-22 system includes zero.
      const targets = rows.filter((r) => r.full);
      inSlices(targets, (r) => {
        if (r.id === leader.id) return;
        const p = paired(r.id, leader.id, sc);
        deltas.set(r.id, p);
        if (!p) return;
        if (tied(p)) { const m = marks.get(r.id); if (m) m.textContent = "≈"; }
        const td = deltaTds.get(r.id);
        if (td) td.replaceChildren(signed(p.delta), " ", h("span", { class: "ci" }, ciText(p)));
      }, () => table.removeAttribute("data-busy"));
    }
    return out;
  }

  // ---------------------------------------------------------------------------------------------
  // Compare

  const METRIC = {
    comet: { label: "COMET-22", idx: 0, digits: 4, better: "high" },
    mx: { label: "MetricX-24", idx: 2, digits: 3, better: "low" },
    mxqe: { label: "MetricX-24 QE", idx: 3, digits: 3, better: "low" },
    chrf: { label: "chrF++", idx: 1, digits: 2, better: "high" },
  };
  // Series colours of their own, so they do not read as the blue local / orange cloud markers.
  const SERIES = ["var(--c1)", "var(--c2)", "var(--c3)", "var(--c4)"];
  function sysOptions(selected, allowNone) {
    const groups = [["local", "Local"], ["cloud", "Cloud"]].map(([k, label]) => h("optgroup", { label },
      SYS.filter((s) => s.kind === k).slice().sort((a, b) => a.name.localeCompare(b.name))
        .map((s) => h("option", { value: s.id, selected: s.id === selected }, devName(s) === s.name ? s.name : `${s.name} (${devName(s)})`))));
    return [allowNone ? h("option", { value: "", selected: !selected }, "(none)") : null, ...groups];
  }
  const swatch = (color) => h("i", { class: "sw", style: "background:" + color, "aria-hidden": "true" });
  function viewCompare() {
    const picked = st.sys.split(",").filter((x) => BY[x]).slice(0, 4);
    while (picked.length < 2) picked.push(SYS.find((s) => !picked.includes(s.id)).id);
    const metric = METRIC[st.metric] || METRIC.comet;
    const out = [h("p", { class: "back" }, h("a", { href: hashFor("leaderboard", { sys: DEFAULT.sys, metric: DEFAULT.metric }) }, "← Leaderboard")),
      h("h1", null, "Compare")];
    const pickers = h("div", { class: "pickers" }, [0, 1, 2, 3].map((i) => h("div", { class: "field" },
      h("label", { class: "lbl", for: "pick-" + i }, i === 0 ? "Baseline" : `System ${i + 1}`),
      h("select", {
        id: "pick-" + i, "data-k": "pick-" + i, onchange: (e) => {
          const next = picked.slice();
          next[i] = e.target.value;
          update({ sys: next.filter(Boolean).filter((x, j, a) => a.indexOf(x) === j).join(",") });
        },
      }, sysOptions(picked[i], i >= 2)))));
    out.push(h("form", { class: "toolbar stack", "aria-label": "Systems and metric", onsubmit: (e) => e.preventDefault() }, pickers,
      h("div", { class: "fieldset" }, typeSeg(),
        seg("Metric", "metric", [["comet", "COMET-22"], ["mx", "MetricX-24"], ["mxqe", "MetricX-24 QE"], ["chrf", "chrF++"]]))));

    const groups = [
      ["All 18 directions", { lang: "all", dir: "both" }],
      ["From English (9)", { lang: "all", dir: "out" }],
      ["Into English (9)", { lang: "all", dir: "into" }],
      ...D.directions.map((d) => [dirName(d), { lang: langOf(d), dir: d.startsWith("en-") ? "out" : "into" }]),
    ];
    const base = picked[0];
    const pending = [];
    const rowsData = [];
    const tbody = h("tbody", null, groups.map(([label, sel], gi) => {
      const sc = scopeOf({ ...sel, type: st.type });
      const vals = picked.map((sid) => {
        const m = measure(sid, sc, metric.idx);
        return m.n === sc.dirs.length ? m.value : null;
      });
      rowsData.push({ label, vals, dir: gi >= 3 ? D.directions[gi - 3] : null });
      const deltas = picked.slice(1).map((sid, i) => {
        const td = h("td", { class: "n" }, "—");
        if (isNum(vals[i + 1]) && isNum(vals[0])) {
          if (st.metric === "comet") { td.textContent = "…"; pending.push({ td, a: sid, b: base, sc }); }
          else td.textContent = signed(vals[i + 1] - vals[0], metric.digits);
        }
        return td;
      });
      return h("tr", { class: gi === 2 ? "group-end" : null }, h("th", { scope: "row", class: "sys" }, gi < 3 ? h("strong", null, label) : label),
        vals.map((v) => h("td", { class: "n" }, fx(v, metric.digits))), deltas);
    }));
    const thead = h("thead", null, h("tr", null,
      h("th", { scope: "col", class: "sys" }, "Selection"),
      picked.map((sid, i) => h("th", { scope: "col", class: "n" }, h("span", { class: "series-name" }, swatch(SERIES[i]), BY[sid].name))),
      picked.slice(1).map((sid) => h("th", { scope: "col", class: "n" }, `${BY[sid].name} − ${BY[base].name}`,
        h("span", { class: "sub" }, st.metric === "comet" ? "Δ [95% CI]" : "Δ")))));

    // Raw scores per direction as a dot plot, above the table.
    const chart = h("div", { class: "chart" });
    out.push(h("h2", null, `${metric.label} by direction`));
    out.push(h("div", { class: "chart-legend" }, picked.map((sid, i) => h("span", null, swatch(SERIES[i]), BY[sid].name))));
    out.push(chart);
    requestAnimationFrame(() => dotPlot(chart, rowsData.filter((r) => r.dir), picked, metric));

    out.push(tableWrap("Comparison table", h("table", { class: "compare" },
      h("caption", { class: "sr-only" }, `${TYPE_NAME[st.type]} · ${metric.label}`),
      thead, tbody)));
    inSlices(pending, (p) => {
      const r = paired(p.a, p.b, p.sc);
      if (!r) { p.td.textContent = "—"; return; }
      p.td.replaceChildren(h("span", { class: tied(r) ? "tie-text" : "pos" }, signed(r.delta)), " ", h("span", { class: "ci" }, ciText(r)));
      p.td.title = tied(r) ? "Interval includes zero: not distinguishable" : (r.delta > 0 ? "Higher than the baseline" : "Lower than the baseline");
    });
    return out;
  }

  // ---------------------------------------------------------------------------------------------
  // Charts

  function linear(d0, d1, r0, r1) {
    const k = (r1 - r0) / (d1 - d0 || 1);
    const f = (v) => r0 + (v - d0) * k;
    f.ticks = (n) => niceTicks(d0, d1, n);
    return f;
  }
  function logScale(d0, d1, r0, r1) {
    const l0 = Math.log(d0), l1 = Math.log(d1), k = (r1 - r0) / (l1 - l0 || 1);
    const f = (v) => r0 + (Math.log(v) - l0) * k;
    f.ticks = () => [0.1, 0.25, 0.5, 1, 2, 4, 8, 16, 32, 64, 1e9, 2e9, 4e9, 8e9, 16e9, 32e9, 64e9].filter((t) => t >= d0 && t <= d1);
    return f;
  }
  function niceTicks(lo, hi, n) {
    const span = hi - lo, raw = span / Math.max(1, n), mag = 10 ** Math.floor(Math.log10(raw));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => span / s <= n) || 10 * mag;
    const out = [];
    for (let t = Math.ceil(lo / step) * step; t <= hi + step * 1e-9; t += step) out.push(+t.toFixed(10));
    return out;
  }
  function frame(container, w, hgt, m, x, y, opts) {
    const svg = sv("svg", { viewBox: `0 0 ${w} ${hgt}`, width: w, height: hgt, role: "img", "aria-label": opts.title });
    svg.append(sv("title", null, opts.title));
    const grid = sv("g", { class: "grid" }), axis = sv("g", { class: "axis" });
    for (const t of y.ticks(opts.yTicks || 6)) {
      const yy = y(t);
      grid.append(sv("line", { x1: m.l, x2: w - m.r, y1: yy, y2: yy }));
      const g = sv("g", { class: "tick" });
      g.append(sv("text", { x: m.l - 6, y: yy + 3.5, "text-anchor": "end" }, opts.yFmt(t)));
      axis.append(g);
    }
    for (const t of x.ticks(opts.xTicks || 6)) {
      const xx = x(t);
      grid.append(sv("line", { x1: xx, x2: xx, y1: m.t, y2: hgt - m.b }));
      const g = sv("g", { class: "tick" });
      g.append(sv("text", { x: xx, y: hgt - m.b + 15, "text-anchor": "middle" }, opts.xFmt(t)));
      axis.append(g);
    }
    axis.append(sv("line", { x1: m.l, x2: w - m.r, y1: hgt - m.b, y2: hgt - m.b }));
    axis.append(sv("line", { x1: m.l, x2: m.l, y1: m.t, y2: hgt - m.b }));
    svg.append(grid, axis);
    svg.append(sv("text", { class: "axis-title", x: m.l + (w - m.l - m.r) / 2, y: hgt - 6, "text-anchor": "middle" }, opts.xLabel));
    svg.append(sv("text", { class: "axis-title", transform: `translate(13 ${m.t + (hgt - m.t - m.b) / 2}) rotate(-90)`, "text-anchor": "middle" }, opts.yLabel));
    container.replaceChildren(svg);
    return svg;
  }
  const textWidth = (t) => t.length * 6.1 + 4;
  // Place labels next to points without overlapping each other; a label that fits nowhere is left to the tooltip.
  function placeLabels(svg, labels, bounds) {
    const boxes = [];
    const overlaps = (b) => boxes.some((o) => b.x < o.x + o.w && o.x < b.x + b.w && b.y < o.y + o.h && o.y < b.y + b.h);
    for (const l of labels) {
      const w = textWidth(l.text), hgt = 13;
      const at = {
        right: { x: l.x + 8, y: l.y - hgt / 2, anchor: "start" },
        left: { x: l.x - 8 - w, y: l.y - hgt / 2, anchor: "end" },
        above: { x: l.x - w / 2, y: l.y - 8 - hgt, anchor: "middle" },
        below: { x: l.x - w / 2, y: l.y + 8, anchor: "middle" },
      };
      const options = (l.prefer || ["right", "left", "above", "below"]).map((k) => at[k]);
      for (const o of options) {
        const b = { x: o.x, y: o.y, w, h: hgt };
        if (b.x < bounds.x0 || b.x + w > bounds.x1 || b.y < bounds.y0 - 4 || b.y + hgt > bounds.y1) continue;
        if (overlaps(b) || (l.avoid || []).some((p) => p.x > b.x - 4 && p.x < b.x + w + 4 && p.y > b.y - 4 && p.y < b.y + hgt + 4)) continue;
        if ((bounds.lines || []).some(([x1, y1, x2, y2]) => Math.max(x1, x2) > b.x - 2 && Math.min(x1, x2) < b.x + w + 2
          && Math.max(y1, y2) > b.y - 2 && Math.min(y1, y2) < b.y + hgt + 2)) continue;
        boxes.push(b);
        const tx = o.anchor === "start" ? b.x : o.anchor === "end" ? b.x + w : b.x + w / 2;
        svg.append(sv("text", { class: "label" + (l.muted ? " muted" : ""), x: tx, y: b.y + hgt - 3, "text-anchor": o.anchor }, l.text));
        break;
      }
    }
  }
  function chartSize(container, ratio, maxH) {
    const w = Math.max(300, Math.floor(container.clientWidth || container.parentElement.clientWidth || 640));
    return [w, Math.min(maxH || 440, Math.max(280, Math.round(w * (w < 520 ? ratio * 1.35 : ratio))))];
  }
  function pointMarks(svg, pts, x, y) {
    for (const p of pts) {
      const g = sv("g", { class: "pt" + (p.id ? " link" : "") });
      const hit = sv("circle", { class: "hit", cx: x(p.x), cy: y(p.y), r: 12, tabindex: "0", role: p.id ? "link" : "img", "aria-label": p.tip.join(", ") });
      const dot = p.hollow
        ? sv("circle", { class: "dot", cx: x(p.x), cy: y(p.y), r: 4.5, style: `fill:var(--bg);stroke:${p.color};stroke-width:2` })
        : p.square
          ? sv("rect", { class: "dot", x: x(p.x) - 4.5, y: y(p.y) - 4.5, width: 9, height: 9, rx: 1.5, style: `fill:${p.color}` })
          : sv("circle", { class: "dot", cx: x(p.x), cy: y(p.y), r: 5, style: `fill:${p.color}` });
      g.append(hit, dot);
      tipTarget(hit, p.tip);
      if (p.id) {
        // A point opens its system's page.
        const go = () => { location.hash = hashFor("system", { id: p.id }); };
        hit.addEventListener("click", go);
        hit.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); go(); } });
      }
      svg.append(g);
    }
  }

  function scatterChart(container, pts, o) {
    const [w, hgt] = chartSize(container, 0.62, 460);
    const m = { l: 58, r: 14, t: 12, b: 44 };
    const xs = pts.map((p) => p.x), ys = pts.map((p) => p.y);
    let x0 = Math.min(...xs), x1 = Math.max(...xs);
    const x = o.log ? logScale(x0 / 1.25, x1 * 1.25, m.l, w - m.r) : linear(Math.min(0, x0), x1 * 1.08, m.l, w - m.r);
    const ypad = (Math.max(...ys) - Math.min(...ys)) * 0.08 || 0.005;
    const y = linear(Math.min(...ys) - ypad, Math.max(...ys) + ypad, hgt - m.b, m.t);
    const svg = frame(container, w, hgt, m, x, y, { ...o, yTicks: 6 });
    const segments = [];
    if (o.frontier) {
      const sorted = pts.slice().sort((a, b) => a.x - b.x || b.y - a.y);
      const front = [];
      let best = -Infinity;
      for (const p of sorted) if (p.y > best) { front.push(p); best = p.y; }
      let d = "";
      front.forEach((p, i) => {
        if (i === 0) d += `M${x(p.x)},${y(p.y)}`;
        else {
          d += `H${x(p.x)}V${y(p.y)}`;
          const q = front[i - 1];
          segments.push([x(q.x), y(q.y), x(p.x), y(q.y)], [x(p.x), y(q.y), x(p.x), y(p.y)]);
        }
      });
      d += `H${w - m.r}`;
      const lastF = front[front.length - 1];
      segments.push([x(lastF.x), y(lastF.y), w - m.r, y(lastF.y)]);
      svg.append(sv("path", { class: "frontier", d }));
      front.forEach((p) => { p.front = true; });
    }
    pointMarks(svg, pts, x, y);
    const avoid = pts.map((p) => ({ x: x(p.x), y: y(p.y) }));
    const labelled = pts.filter((p) => p.front || p.label).sort((a, b) => b.y - a.y);
    placeLabels(svg, labelled.map((p) => ({ x: x(p.x), y: y(p.y), text: p.name, prefer: ["left", "above", "below", "right"], avoid: avoid.filter((q) => q.x !== x(p.x) || q.y !== y(p.y)) })),
      { x0: m.l + 2, x1: w - m.r, y0: m.t, y1: hgt - m.b, lines: segments });
    return pts;
  }

  function dotPlot(container, rows, picked, metric) {
    const w = Math.max(300, container.clientWidth || 640);
    const narrow = w < 600;
    const rowH = 22, m = { l: narrow ? 74 : 214, r: 16, t: 8, b: 40 };
    const hgt = m.t + m.b + rows.length * rowH;
    const all = rows.flatMap((r) => r.vals.filter(isNum));
    if (!all.length) { container.replaceChildren(h("p", { class: "note" }, "No scores in this selection.")); return; }
    const pad = (Math.max(...all) - Math.min(...all)) * 0.06 || 0.01;
    const x = linear(Math.min(...all) - pad, Math.max(...all) + pad, m.l, w - m.r);
    const svg = sv("svg", { viewBox: `0 0 ${w} ${hgt}`, width: w, height: hgt, role: "img", "aria-label": `${metric.label} by direction for the selected systems` });
    const grid = sv("g", { class: "grid" }), axis = sv("g", { class: "axis" });
    for (const t of niceTicks(Math.min(...all) - pad, Math.max(...all) + pad, Math.max(3, Math.floor(w / 110)))) {
      grid.append(sv("line", { x1: x(t), x2: x(t), y1: m.t, y2: hgt - m.b }));
      const g = sv("g", { class: "tick" });
      g.append(sv("text", { x: x(t), y: hgt - m.b + 15, "text-anchor": "middle" }, t.toFixed(metric.digits === 2 ? 0 : metric.digits - 1)));
      axis.append(g);
    }
    svg.append(grid, axis);
    rows.forEach((r, i) => {
      const yy = m.t + i * rowH + rowH / 2;
      svg.append(sv("text", { class: "label", x: m.l - 8, y: yy + 4, "text-anchor": "end" }, narrow ? dirShort(r.dir) : r.label));
      const vs = r.vals.filter(isNum);
      if (vs.length > 1) svg.append(sv("line", { x1: x(Math.min(...vs)), x2: x(Math.max(...vs)), y1: yy, y2: yy, style: "stroke:var(--grid);stroke-width:2" }));
      r.vals.forEach((v, j) => {
        if (!isNum(v)) return;
        const g = sv("g", { class: "pt" });
        const hit = sv("circle", { class: "hit", cx: x(v), cy: yy, r: 10, tabindex: "0" });
        g.append(hit, sv("circle", { class: "dot", cx: x(v), cy: yy, r: 5, style: `fill:${SERIES[j]}` }));
        tipTarget(hit, [fx(v, metric.digits), BY[picked[j]].name, r.label]);
        svg.append(g);
      });
    });
    svg.append(sv("text", { class: "axis-title", x: m.l + (w - m.l - m.r) / 2, y: hgt - 6, "text-anchor": "middle" }, metric.label + (metric.better === "low" ? " (lower is better)" : " (higher is better)")));
    container.replaceChildren(svg);
  }

  // ---------------------------------------------------------------------------------------------
  // Trade-offs: quality vs memory, speed and model size

  const hollowLegend = (title) => h("p", { class: "chart-legend" },
    h("span", { title }, h("i", { class: "sw hollow", "aria-hidden": "true" }), "partial coverage"));

  function viewTradeoffs() {
    const sc = scopeOf(st);
    const out = [h("h1", { class: "sr-only" }, "Speed & memory"), filters({ kind: false, mem: false })];
    const rows = rowsFor(st).filter((r) => r.sys.kind === "local" && (r.full || (st.full !== "1" && r.cover > 0)));
    const speedKey = st.type === "sentence" ? "ss" : st.type === "passage" ? "sp" : null;
    const speedOfRow = (r) => (speedKey ? r[speedKey] : isNum(r.ss) && isNum(r.sp) ? (r.ss + r.sp) / 2 : null);
    const speedHelp = st.type === "overall" ? "Seconds per item: the mean of the sentence and passage medians" : `Median seconds per ${st.type}`;
    const speedLabel = `Seconds per ${st.type === "overall" ? "item" : st.type} (log)`;
    const tipLines = (r, extra) => [r.sys.name + (r.full ? "" : " *"), `COMET-22 ${fx(r.comet, 4)} (${scopeText(sc, st)})`, extra, `${r.sys.developer} · ${r.sys.quantization || r.sys.runtime || ""}`];
    const memPts = rows.filter((r) => isNum(r.mem) && isNum(r.comet)).map((r) => ({
      x: r.mem, y: r.comet, name: r.sys.name, color: "var(--local)", hollow: !r.full, tip: tipLines(r, `Peak memory ${fx(r.mem, 2)} GiB`), id: r.id,
    }));
    const spdPts = rows.filter((r) => isNum(speedOfRow(r)) && isNum(r.comet)).map((r) => ({
      x: speedOfRow(r), y: r.comet, name: r.sys.name, color: "var(--local)", hollow: !r.full, tip: tipLines(r, `${fx(speedOfRow(r), 2)} s per ${st.type === "overall" ? "item" : st.type}`), id: r.id,
    }));
    const c1 = h("div", { class: "chart" }), c2 = h("div", { class: "chart" });
    const frontierHelp = "The line traces the Pareto frontier.";
    out.push(h("div", { class: "grid2" },
      h("section", { class: "card", "aria-labelledby": "t-mem" }, h("h2", { id: "t-mem", title: `COMET-22 against peak memory. ${frontierHelp}` }, "COMET-22 vs memory"), c1),
      h("section", { class: "card", "aria-labelledby": "t-spd" }, h("h2", { id: "t-spd", title: `COMET-22 against speed. ${speedHelp}. ${frontierHelp}` }, "COMET-22 vs speed"), c2)));
    if (memPts.concat(spdPts).some((p) => p.hollow)) out.push(hollowLegend("Partial coverage: averaged over the directions covered"));
    requestAnimationFrame(() => {
      if (memPts.length) scatterChart(c1, memPts, { title: "COMET-22 against peak memory", log: true, frontier: true, xLabel: "Peak memory (GiB, log)", yLabel: "COMET-22", xFmt: (t) => String(t), yFmt: (t) => t.toFixed(3) });
      if (spdPts.length) scatterChart(c2, spdPts, { title: `COMET-22 against seconds per ${st.type === "overall" ? "item" : st.type}`, log: true, frontier: true, xLabel: speedLabel, yLabel: "COMET-22", xFmt: (t) => String(t), yFmt: (t) => t.toFixed(3) });
    });
    // Table of the same points, folded.
    const front = (pts) => {
      const s = pts.slice().sort((a, b) => a.x - b.x || b.y - a.y); let best = -Infinity; const ids = new Set();
      for (const p of s) if (p.y > best) { ids.add(p.id); best = p.y; }
      return ids;
    };
    const fm = front(memPts.filter((p) => !p.hollow)), fs = front(spdPts.filter((p) => !p.hollow));
    const tableRows = rows.filter((r) => isNum(r.comet)).sort((a, b) => b.comet - a.comet);
    const trs = tableRows.map((r) => h("tr", null,
      h("td", { class: "sys" }, sysLink(r.sys)), h("td", { class: "n" }, fx(r.comet, 4), r.full ? null : h("span", { class: "star" }, "*")),
      h("td", { class: "n" + (isNum(r.mem) ? "" : " na") }, isNum(r.mem) ? fx(r.mem, 2) : "not measured"), h("td", { class: "n" }, fx(speedOfRow(r), 2)),
      h("td", null, [fm.has(r.id) ? "memory" : null, fs.has(r.id) ? "speed" : null].filter(Boolean).join(", ") || "")));
    out.push(h("details", { class: "fold" }, h("summary", null, `Table (${tableRows.length})`),
      tableWrap("COMET-22, memory and speed of local systems", h("table", null,
        h("caption", { class: "sr-only" }, scopeText(sc, st)),
        h("thead", null, h("tr", null, h("th", { scope: "col", class: "sys" }, "System"), h("th", { scope: "col", class: "n" }, "COMET-22"),
          h("th", { scope: "col", class: "n" }, "Peak memory (GiB)"), h("th", { scope: "col", class: "n", title: speedHelp }, st.type === "overall" ? "s per item" : `s per ${st.type}`),
          h("th", { scope: "col" }, "On the frontier"))),
        h("tbody", null, trs)))));
    out.push(sizeSection(sc));
    return out;
  }

  // Model size: each local family by total parameters, against DeepL API and the top cloud system on COMET-22.
  function sizeSection(sc) {
    const out = [h("h2", { id: "sizes", tabindex: "-1", title: "COMET-22 of the local model families by total parameters; dashed lines mark DeepL API and the top cloud system on COMET-22" }, "COMET-22 vs parameters")];
    const fams = Object.entries(D.families);
    const colors = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)", "var(--s5)", "var(--s6)"];
    const series = fams.map(([fam, ids], i) => ({
      fam, color: colors[i % colors.length], pts: ids.map((id) => {
        const m = measure(id, sc, 0);
        return { id, x: BY[id].parameters, y: m.value, n: m.n, full: m.n === sc.dirs.length };
      }).filter((p) => isNum(p.y)),
    }));
    const rows = rowsFor(st);
    const cloud = rows.filter((r) => r.sys.kind === "cloud" && r.full).sort((a, b) => b.comet - a.comet);
    const refs = [];
    const deepl = rows.find((r) => r.id === "deepl-api" && r.full);
    if (cloud[0]) refs.push({ name: cloud[0].sys.name + " (top cloud, COMET-22)", short: "Top cloud", y: cloud[0].comet });
    if (deepl && (!cloud[0] || cloud[0].id !== deepl.id)) refs.push({ name: "DeepL API", short: "DeepL API", y: deepl.comet });
    const chart = h("div", { class: "chart" });
    out.push(h("div", { class: "card" }, chart));
    if (series.some((s) => s.pts.some((p) => !p.full))) out.push(hollowLegend("Partial coverage: averaged over the directions covered"));
    requestAnimationFrame(() => {
      const [w, hgt] = chartSize(chart, 0.5, 460);
      const narrow = w < 520;
      const m = { l: 58, r: narrow ? 112 : 180, t: 12, b: 44 };
      const pts = series.flatMap((s) => s.pts);
      if (!pts.length) { chart.replaceChildren(h("p", { class: "note" }, "No family covers this selection.")); return; }
      const ys = pts.map((p) => p.y).concat(refs.map((r) => r.y));
      const pad = (Math.max(...ys) - Math.min(...ys)) * 0.06 || 0.005;
      const x = logScale(0.6e9, 50e9, m.l, w - m.r);
      const y = linear(Math.min(...ys) - pad, Math.max(...ys) + pad, hgt - m.b, m.t);
      const svg = frame(chart, w, hgt, m, x, y, { title: "COMET-22 by total parameters, per model family", xLabel: "Total parameters (log)", yLabel: "COMET-22", xFmt: (t) => (t / 1e9) + "B", yFmt: (t) => t.toFixed(3) });
      for (const r of refs) svg.append(sv("line", { class: "ref-line", x1: m.l, x2: w - m.r, y1: y(r.y), y2: y(r.y) }));
      for (const s of series) {
        if (s.pts.length > 1) svg.append(sv("path", { class: "series", d: s.pts.map((p, i) => (i ? "L" : "M") + x(p.x) + "," + y(p.y)).join(""), style: `stroke:${s.color}` }));
        pointMarks(svg, s.pts.map((p) => ({
          x: p.x, y: p.y, color: s.color, hollow: !p.full, id: p.id,
          tip: [BY[p.id].name, `COMET-22 ${fx(p.y, 4)}`, `${(p.x / 1e9).toFixed(1)}B total parameters${BY[p.id].moe ? " (mixture of experts)" : ""}`, `${p.n} of ${sc.dirs.length} directions`],
        })), x, y);
      }
      // Labels in the right margin, in the order of the line ends, stacked so they do not overlap, each with
      // its line's colour (several families end within a few pixels of each other).
      const labels = series.filter((s) => s.pts.length).map((s) => {
        const last = s.pts[s.pts.length - 1];
        return { y: y(last.y), text: s.fam, color: s.color };
      }).concat(refs.map((r) => ({ y: y(r.y), text: narrow ? r.short : r.name, ref: true })))
        .sort((a, b) => a.y - b.y);
      const gap = 14, top = m.t + 4, bottom = hgt - m.b;
      let prev = -Infinity;
      for (const l of labels) { l.ly = Math.max(l.y, prev + gap, top); prev = l.ly; }
      for (let i = labels.length - 1, next = bottom + gap; i >= 0; i--) { labels[i].ly = Math.min(labels[i].ly, next - gap); next = labels[i].ly; }
      const lx = w - m.r + 8;
      for (const l of labels) {
        svg.append(sv("line", { class: l.ref ? "ref-line" : "series", x1: lx, x2: lx + 14, y1: l.ly, y2: l.ly, style: l.ref ? null : `stroke:${l.color};stroke-width:3` }));
        svg.append(sv("text", { class: "label" + (l.ref ? " muted" : ""), x: lx + 19, y: l.ly + 3.5 }, l.text));
      }
    });
    // Table: sizes with the paired step to the next size, folded.
    const trs = [];
    const steps = [];
    for (const s of series) {
      s.pts.forEach((p, i) => {
        const td = h("td", { class: "n" }, i === 0 ? "" : "…");
        if (i > 0) steps.push({ td, a: p.id, b: s.pts[i - 1].id });
        trs.push(h("tr", null, h("td", null, s.fam), h("td", { class: "sys" }, sysLink(BY[p.id])),
          h("td", { class: "n" }, (p.x / 1e9).toFixed(1) + "B" + (BY[p.id].moe ? " MoE" : "")),
          h("td", { class: "n" }, fx(p.y, 4), p.full ? null : h("span", { class: "star" }, "*")), h("td", { class: "n" }, `${p.n}/${sc.dirs.length}`), td));
      });
    }
    out.push(h("details", { class: "fold" }, h("summary", null, "Scaling steps"),
      tableWrap("Model sizes", h("table", null, h("caption", { class: "sr-only" }, `${scopeText(sc, st)}. Each step is compared on the directions both sizes cover, with a paired 95% interval.`),
        h("thead", null, h("tr", null, ["Family", "System", "Total parameters", "COMET-22", "Directions", "Δ vs next smaller [95% CI]"].map((t, i) => h("th", { scope: "col", class: i >= 2 ? "n" : (i === 1 ? "sys" : null) }, t)))),
        h("tbody", null, trs)))));
    inSlices(steps, (p) => {
      const common = { ...sc, dirs: sc.dirs.filter((d) => sc.types.every((t) => cell(p.a, t, d) && cell(p.b, t, d))) };
      common.key = common.dirs.join(",") + "|" + sc.types.join("");
      const r = paired(p.a, p.b, common);
      p.td.replaceChildren(r ? signed(r.delta) : "—", " ", h("span", { class: "ci" }, ciText(r)));
    });
    return out;
  }

  // ---------------------------------------------------------------------------------------------
  // Languages

  function viewLanguages() {
    // The kind filter only applies to the heat map, so its control sits there; Reset clears it too.
    const out = [h("h1", { class: "sr-only" }, "Languages"), filters({ kind: false, lang: false, mem: false, full: false }, ["kind"])];
    const trs = [], pend = [];
    for (const l of D.languages) {
      const s2 = { ...st, lang: l.code };
      const sc = scopeOf(s2);
      const rows = rowsFor(s2).filter((r) => r.full);
      const best = (k) => rows.filter((r) => r.sys.kind === k).sort((a, b) => b.comet - a.comet)[0];
      const lo = best("local"), cl = best("cloud");
      const td = h("td", { class: "n" }, "…");
      if (lo && cl) pend.push({ td, a: cl.id, b: lo.id, sc });
      else td.textContent = "—";
      trs.push(h("tr", null, h("th", { scope: "row", class: "sys" }, `${l.name}${st.dir === "both" ? "" : st.dir === "out" ? " (from English)" : " (into English)"}`),
        h("td", null, lo ? markedName(lo.sys, sysLink(lo.sys)) : "—"), h("td", { class: "n" }, lo ? fx(lo.comet, 4) : "—"),
        h("td", null, cl ? markedName(cl.sys, sysLink(cl.sys)) : "—"), h("td", { class: "n" }, cl ? fx(cl.comet, 4) : "—"), td));
    }
    out.push(tableWrap("Leaders by language", h("table", { class: "leaders" },
      h("caption", { class: "sr-only" }, `${TYPE_NAME[st.type]} · COMET-22`),
      h("thead", null, h("tr", null, ["Language", "Top local on COMET-22", "COMET-22", "Top cloud on COMET-22", "COMET-22", "Cloud − local [95% CI]"].map((t, i) => h("th", { scope: "col", class: [2, 4, 5].includes(i) ? "n" : (i === 0 ? "sys" : null) }, t)))),
      h("tbody", null, trs))));
    out.push(h("p", { class: "legend-line" }, h("span", null, "Muted = tied (95% interval)")));
    inSlices(pend, (p) => {
      const r = paired(p.a, p.b, p.sc);
      if (!r) { p.td.textContent = "—"; return; }
      p.td.classList.toggle("muted-cell", tied(r));
      p.td.title = tied(r) ? "Interval includes zero: not distinguishable" : r.delta > 0 ? "Interval excludes zero: cloud higher" : "Interval excludes zero: local higher";
      p.td.replaceChildren(signed(r.delta), " ", h("span", { class: "ci" }, ciText(r)));
    });

    // Heat map
    out.push(h("h2", null, "All systems"));
    out.push(h("div", { class: "toolbar slim" }, seg("Columns", "by", [["direction", "18 directions"], ["pair", "9 languages"]]), kindSeg()));
    const cols = st.by === "pair"
      ? D.languages.map((l) => {
        const sc = scopeOf({ lang: l.code, dir: st.dir, type: st.type });
        return { label: l.name, title: st.dir === "both" ? `English ↔ ${l.name}` : dirName(sc.dirs[0]), sc };
      })
      : D.directions.filter((d) => st.dir === "both" || (st.dir === "out") === d.startsWith("en-")).map((d) => ({ label: dirShort(d), title: dirName(d), sc: scopeOf({ lang: langOf(d), dir: d.startsWith("en-") ? "out" : "into", type: st.type }) }));
    const sysRows = SYS.filter((s) => st.kind === "all" || s.kind === st.kind).map((s) => {
      const vals = cols.map((c) => { const m = measure(s.id, c.sc, 0); return m.n === c.sc.dirs.length ? m.value : null; });
      const overall = measure(s.id, scopeOf({ ...st, lang: "all" }), 0);
      return { s, vals, order: overall.value, full: vals.every(isNum) };
    }).filter((r) => r.vals.some(isNum)).sort((a, b) => (b.full - a.full) || (b.order || 0) - (a.order || 0));
    const tops = cols.map((c, i) => Math.max(...sysRows.map((r) => r.vals[i]).filter(isNum)));
    const step = (gap) => (gap <= 0.002 ? 1 : gap <= 0.005 ? 2 : gap <= 0.01 ? 3 : gap <= 0.02 ? 4 : 5);
    out.push(h("div", { class: "heat-legend", "aria-hidden": "true" }, "Gap to best:",
      [["≤ 0.002", 1], ["≤ 0.005", 2], ["≤ 0.010", 3], ["≤ 0.020", 4], ["> 0.020", 5]].map(([t, k]) => h("span", null, h("i", { class: "h" + k }), t)),
      st.kind === "all" ? [h("span", { class: "kbar local" }, "Local"), h("span", { class: "kbar cloud" }, "Cloud")] : null));
    out.push(tableWrap("COMET-22 heat map", h("table", { class: "heat" + (st.by === "pair" ? " pairs" : "") },
      h("caption", { class: "sr-only" }, `${st.type === "overall" ? "" : TYPE_NAME[st.type] + " · "}COMET-22 · sorted by COMET-22 over all languages · — = not measured`),
      h("thead", null, h("tr", null, h("th", { scope: "col", class: "sys" }, "System"), cols.map((c) => h("th", { scope: "col", class: "dh", title: c.title }, c.label)))),
      h("tbody", null, sysRows.map((r) => h("tr", { class: "k-" + r.s.kind }, h("th", { scope: "row", class: "sys" }, markedName(r.s,
        [h("a", { href: hashFor("system", { id: r.s.id }), title: shortName(r.s) === r.s.name ? null : r.s.name }, shortName(r.s)),
          h("span", { class: "sr-only" }, r.s.kind === "local" ? " (local)" : " (cloud)")])),
        r.vals.map((v, i) => isNum(v)
          ? h("td", { class: "h h" + step(tops[i] - v), title: `${r.s.name} · ${cols[i].title} · COMET-22 ${v.toFixed(4)}` }, v.toFixed(3).replace(/^0/, ""))
          : h("td", { class: "h na", title: `${r.s.name} · ${cols[i].title}: not measured` }, "—"))))))));
    return out;
  }

  // ---------------------------------------------------------------------------------------------
  // Metric disagreement

  function ranks(values, better) {
    const idx = values.map((v, i) => [v, i]).filter(([v]) => isNum(v)).sort((a, b) => (better === "low" ? a[0] - b[0] : b[0] - a[0]));
    const out = values.map(() => null);
    let i = 0;
    while (i < idx.length) {
      let j = i;
      while (j + 1 < idx.length && idx[j + 1][0] === idx[i][0]) j++;
      for (let k = i; k <= j; k++) out[idx[k][1]] = (i + j) / 2 + 1;
      i = j + 1;
    }
    return out;
  }
  function spearman(a, b) {
    const pairs = a.map((x, i) => [x, b[i]]).filter(([x, y]) => isNum(x) && isNum(y));
    if (pairs.length < 3) return null;
    const ma = mean(pairs.map((p) => p[0])), mb = mean(pairs.map((p) => p[1]));
    let num = 0, da = 0, db = 0;
    for (const [x, y] of pairs) { num += (x - ma) * (y - mb); da += (x - ma) ** 2; db += (y - mb) ** 2; }
    return num / Math.sqrt(da * db);
  }
  function viewMetrics() {
    const sc = scopeOf(st);
    const judgeRank = judgeRankable(sc);
    const out = [h("h1", null, "Where the metrics disagree"),
      h("p", { class: "lede" }, "How the order of systems changes between COMET-22, MetricX-24 and the LLM judge."),
      filters({ full: false })];
    const rows = rowsFor(st).filter((r) => passes(r, st) && r.full);
    const allMetrics = [
      { key: "comet", label: "COMET-22", better: "high", fmt: (v) => fx(v, 4) },
      { key: "mx", label: "MetricX-24", better: "low", fmt: (v) => fx(v, 3) },
      { key: "mxqe", label: "MetricX-24 QE", better: "low", fmt: (v) => fx(v, 3) },
      { key: "chrf", label: "chrF++", better: "high", fmt: (v) => fx(v, 2) },
      { key: "judge", label: "Judge vs DeepL API", better: "high", fmt: (v) => pct(v), judge: true },
      { key: "ef", label: "Error-free", better: "high", fmt: (v) => pct(v), judge: true },
    ];
    // Judge columns are ranked, charted and correlated only with enough sampled items.
    const metrics = allMetrics.filter((m) => judgeRank || !m.judge);
    const R = Object.fromEntries(metrics.map((m) => [m.key, ranks(rows.map((r) => r[m.key]), m.better)]));
    const order = rows.map((r, i) => i).sort((a, b) => R.comet[a] - R.comet[b]);

    // Bump chart: COMET-22 → MetricX-24 → judge → error-free ranks.
    const chartMetrics = judgeRank ? metrics.filter((m) => ["comet", "mx", "judge", "ef"].includes(m.key)) : metrics;
    const chart = h("div", { class: "chart" });
    out.push(h("div", { class: "chart-legend" }, h("span", { class: "kind local" }, "Local"), h("span", { class: "kind cloud" }, "Cloud"),
      h("span", null, "Rank 1 at the top; hover or focus a line to follow one system")));
    out.push(h("div", { class: "card" }, chart));
    requestAnimationFrame(() => {
      const w = Math.max(320, chart.clientWidth || 640);
      const narrow = w < 640;
      const m = { l: narrow ? 96 : 190, r: narrow ? 96 : 190, t: 50, b: 10 };
      const n = rows.length;
      const hgt = m.t + m.b + Math.max(1, n) * (narrow ? 15 : 17);
      const xs = chartMetrics.map((_, i) => m.l + (i * (w - m.l - m.r)) / (chartMetrics.length - 1));
      const y = (rk) => m.t + (rk - 1) * ((hgt - m.t - m.b) / Math.max(1, n - 1));
      const svg = sv("svg", { viewBox: `0 0 ${w} ${hgt}`, width: w, height: hgt, role: "img", class: "bumps", "aria-label": "Ranks of the same systems under COMET-22, MetricX-24, the judge and error-free share" });
      chartMetrics.forEach((mm, i) => {
        svg.append(sv("line", { x1: xs[i], x2: xs[i], y1: m.t - 6, y2: hgt - m.b + 4, style: "stroke:var(--grid)" }));
        svg.append(sv("text", { class: "axis-title", x: xs[i], y: 14, "text-anchor": "middle" }, mm.label));
        svg.append(sv("text", { class: "label muted", x: xs[i], y: 28, "text-anchor": "middle" }, mm.better === "low" ? "lower is better" : "higher is better"));
      });
      // Positions: ranks with ties broken by COMET-22, so tied systems do not share a line.
      const P = Object.fromEntries(chartMetrics.map((mm) => {
        const idx = rows.map((r, i) => i).filter((i) => R[mm.key][i] != null).sort((a, b) => R[mm.key][a] - R[mm.key][b] || R.comet[a] - R.comet[b]);
        const pos = rows.map(() => null);
        idx.forEach((i, k) => { pos[i] = k + 1; });
        return [mm.key, pos];
      }));
      const groups = [];
      const focusOn = (g) => { svg.classList.add("hl"); groups.forEach((o) => o.classList.toggle("on", o === g)); };
      const focusOff = () => { svg.classList.remove("hl"); groups.forEach((o) => o.classList.remove("on")); };
      rows.forEach((r, i) => {
        const color = r.sys.kind === "local" ? "var(--local)" : "var(--cloud)";
        const g = sv("g", { class: "bump", tabindex: "0", role: "img", "aria-label": `${r.sys.name}: ` + chartMetrics.map((mm) => `${mm.label} rank ${R[mm.key][i] ?? "n/a"}`).join(", ") });
        const pts = chartMetrics.map((mm, k) => (P[mm.key][i] != null ? [xs[k], y(P[mm.key][i])] : null));
        let d = "", pen = false;
        for (const p of pts) { if (!p) { pen = false; continue; } d += (pen ? "L" : "M") + p[0] + "," + p[1]; pen = true; }
        g.append(sv("path", { class: "series", d, style: `stroke:${color}` }));
        pts.forEach((p) => { if (p) g.append(sv("circle", { class: "dot", cx: p[0], cy: p[1], r: 3.5, style: `fill:${color}` })); });
        const short = narrow ? shortName(r.sys).slice(0, 15) : shortName(r.sys);
        if (pts[0]) g.append(sv("text", { class: "label", x: pts[0][0] - 8, y: pts[0][1] + 3.5, "text-anchor": "end" }, short));
        const lastK = pts.length - 1;
        if (pts[lastK]) g.append(sv("text", { class: "label", x: pts[lastK][0] + 8, y: pts[lastK][1] + 3.5 }, short));
        const lines = [r.sys.name, ...chartMetrics.map((mm) => `${mm.label}: ${r.id === J.reference && mm.key === "judge" ? "baseline" : mm.fmt(r[mm.key])} (rank ${R[mm.key][i] ?? "—"})` + (mm.judge && (mm.key === "judge" ? r.judgeE : r.efE) ? `, n ${(mm.key === "judge" ? r.judgeE : r.efE).n}` : ""))];
        g.addEventListener("pointerenter", (e) => { focusOn(g); showTip(e, lines); });
        g.addEventListener("pointermove", (e) => showTip(e, lines));
        g.addEventListener("pointerleave", () => { focusOff(); hideTip(); });
        g.addEventListener("focus", (e) => { focusOn(g); showTip(e, lines); });
        g.addEventListener("blur", () => { focusOff(); hideTip(); });
        groups.push(g);
        svg.append(g);
      });
      chart.replaceChildren(svg);
    });

    // Correlations
    const corr = h("table", { class: "corr" }, h("caption", null, `${plural(rows.length, "system")} · 1 = same order`),
      h("thead", null, h("tr", null, h("th", { scope: "col" }, ""), metrics.map((mm) => h("th", { scope: "col", class: "n" }, mm.label)))),
      h("tbody", null, metrics.map((a) => h("tr", null, h("th", { scope: "row" }, a.label),
        metrics.map((b) => { const v = spearman(R[a.key], R[b.key]); return h("td", { class: "n" }, isNum(v) ? v.toFixed(2) : "—"); })))));
    out.push(h("h2", null, "Rank correlation (Spearman)"));
    out.push(tableWrap("Rank correlations", corr));

    // Scores with ranks, folded; n in the tooltips.
    out.push(h("details", { class: "fold" }, h("summary", null, "All scores and ranks"),
      tableWrap("Scores and ranks by metric", h("table", null,
        h("caption", null, `${scopeText(sc, st)} · systems with full coverage, in COMET-22 order · score (rank)${judgeRank ? "" : `. Fewer than ${JUDGE_MIN} sampled items here: the judge is not ranked`}.`),
        h("thead", null, h("tr", null, h("th", { scope: "col", class: "sys" }, "System"), allMetrics.map((mm) => h("th", { scope: "col", class: "n" }, mm.label,
          h("span", { class: "arr", "aria-hidden": "true" }, mm.better === "low" ? "↓" : "↑"))))),
        h("tbody", null, order.map((i) => h("tr", null, h("td", { class: "sys" }, h("span", { class: "kind " + rows[i].sys.kind }, sysLink(rows[i].sys))),
          allMetrics.map((mm) => {
            const r = rows[i];
            if (mm.key === "judge" && r.id === J.reference) return h("td", { class: "n na", title: "The baseline of the pairwise judge" }, "baseline");
            const e = mm.key === "judge" ? r.judgeE : mm.key === "ef" ? r.efE : null;
            return h("td", { class: "n", title: e ? `n ${e.n}` : null }, mm.fmt(r[mm.key]), R[mm.key] && R[mm.key][i] != null ? h("span", { class: "nn" }, `(${R[mm.key][i]})`) : null);
          }))))))));
    return out;
  }

  // ---------------------------------------------------------------------------------------------
  // One system

  function viewSystem() {
    const sys = BY[st.id];
    if (!sys) return [h("h1", null, "System not found"), h("p", null, h("a", { href: "#leaderboard" }, "Back to the leaderboard"))];
    const items = [
      ["Developer", devName(sys) === sys.name ? null : devName(sys)], ["Kind", sys.kind === "local" ? "Local" : "Cloud"], ["Family", sys.family === sys.developer ? null : sys.family],
      ["Total parameters", sys.parameters ? `${(sys.parameters / 1e9).toFixed(2)}B${sys.moe ? " (mixture of experts)" : ""}` : null],
      ["Weights", sys.format ? `${sys.format}${sys.quantization ? ", " + sys.quantization : ""}${sys.download ? `, ${fx(gib(sys.download), 2)} GiB` : ""}` : null],
      ["Licence", sys.license], ["Runtime", sys.runtime], ["Client", sys.client ? `${sys.client} (${sys.via})` : null],
      ["Reasoning effort", sys.reasoning], ["Prompt profile", sys.prompt],
      ["Items per request", sys.per_request ? `${sys.per_request.sentence} sentence(s) / ${sys.per_request.passage} passage(s)` : null],
      ["Concurrency", sys.concurrent],
      ["Unsupported languages", sys.unsupported && sys.unsupported.length ? sys.unsupported.map((c) => LANG[c] || c).join(", ") : sys.support_note || (sys.unsupported ? "none" : null)],
      ["Completion", `${sys.completion.scored.toLocaleString("en")} of ${sys.completion.attempted.toLocaleString("en")} items scored`],
    ];
    if (sys.kind === "local") {
      items.push(["Peak memory", isNum(sys.memory) ? `${fx(sys.memory, 2)} GiB` : "not measured (system services)"]);
      if (sys.speed) items.push(["Median seconds", `${fx(sys.speed.s && sys.speed.s.median, 2)} per sentence (p90 ${fx(sys.speed.s && sys.speed.s.p90, 2)}), ${fx(sys.speed.p && sys.speed.p.median, 2)} per passage (p90 ${fx(sys.speed.p && sys.speed.p.p90, 2)})`]);
      if (isNum(sys.load)) items.push(["Load time", `${fx(sys.load, 1)} s`]);
      if (sys.flagged) items.push(["Speed repetitions flagged", `${sys.flagged} of 3 (measurement conditions not met during the repetition; values kept)`]);
    } else if (sys.reference) {
      const r = sys.reference;
      const ref = (x, what) => (x ? `${what}: ${fx(x.seconds, 2)} s per item, ${isNum(x.usd) ? x.usd.toFixed(3) + " USD per 1,000 items (estimated)" : "cost not estimated"}` : null);
      items.push(["Batched time and cost", [ref(r.s, "sentences"), ref(r.p, "passages")].filter(Boolean).join("; ")]);
    }
    const dl = h("dl", { class: "meta" }, items.filter(([, v]) => v != null && v !== "").flatMap(([k, v]) => [h("dt", null, k), h("dd", null, String(v))]));

    // Tiles over every direction, both text types: the Overall score and its three pillars first, then the
    // other default columns. Ranks: the Overall score among the systems with one, COMET-22 among full coverage.
    const sAll = { ...DEFAULT };
    const rows = rowsFor(sAll);
    const me = rows.find((r) => r.id === sys.id);
    const ranked = rows.filter((r) => r.full).sort((a, b) => b.comet - a.comet);
    const pos = ranked.findIndex((r) => r.id === sys.id);
    const byOverall = rows.filter((r) => isNum(r.overall)).sort((a, b) => b.overall - a.overall || b.comet - a.comet);
    const oPos = byOverall.findIndex((r) => r.id === sys.id);
    const js = J.systems[sys.id] || {};
    const jsAll = js.all || {};
    const tile = (label, value, sub, title) => h("div", { class: "tile", title: title || null }, h("div", { class: "t-lbl" }, label), h("div", { class: "t-val" }, value), sub ? h("div", { class: "t-sub" }, sub) : null);
    const partialSub = me.full ? null : `${me.cover} of ${me.total} directions; not ranked`;
    let speedTile;
    if (sys.kind === "local") {
      const ss = sys.speed && sys.speed.s ? sys.speed.s.median : null;
      speedTile = tile("Speed and memory", `${fx(ss, 2)} s · ${isNum(sys.memory) ? fx(sys.memory, 2) + " GiB" : "—"}`,
        isNum(sys.memory) ? "per sentence · peak memory" : "per sentence · memory not measured");
    } else {
      const r = sys.reference && sys.reference.s;
      speedTile = tile("Batched time", r ? `${fx(r.seconds, 2)} s` : "—", r ? "per sentence, batched requests" : null, r ? REF_DETAIL : null);
    }
    const oe = sys.overall;
    let overallTile = null;
    if (oe) {
      const cov = oe.coverage < NDIR ? ` · mean over ${oe.coverage} of ${NDIR} directions (no ${langList(oe.missing_languages)})` : " · mean of the three pillars";
      overallTile = isNum(oe.overall)
        ? tile("Overall ↑", fx(oe.overall, 1), `rank ${oPos + 1} of ${byOverall.length}${cov}`, COLUMN_HELP.overall)
        : tile("Overall ↑", "—", `No Overall score: ${noOverallReason(me)}`, COLUMN_HELP.overall);
    }
    const ef = jsAll.ef;
    const efSub = !ef ? null : ef.directions && ef.directions < NDIR ? `${ef.directions} of ${NDIR} directions`
      : ef.ci ? `95% interval ${pct(ef.ci[0], 1)}–${pct(ef.ci[1], 1)}` : null;
    const hard = sys.ltb;
    const hardSub = !hard ? null : `95% interval ${pct(hard.ci[0], 1)}–${pct(hard.ci[1], 1)} · ${hard.items} items`
      + (hard.all ? ` in its ${hard.directions} directions; ${pct(hard.all.rate, 1)} on all ${hard.all.items}` : "");
    const hardTile = HAS_HARD ? tile("Hard cases ↑", hard ? pct(hard.rate, 1) : "—", hardSub, COLUMN_HELP.hard) : null;
    const tiles = h("div", { class: "tiles sys" },
      overallTile,
      tile("COMET-22 ↑", fx(me.comet, 4), me.full ? `rank ${pos + 1} of ${ranked.length} on COMET-22` : partialSub),
      tile("Error-free ↑", ef ? pct(ef.value, 1) : "—", efSub, COLUMN_HELP.ef),
      hardTile,
      tile("MetricX-24 ↓", fx(me.mx, 3), partialSub),
      tile(`vs ${REF} ↑`, sys.id === J.reference ? "baseline" : jsAll.vs ? pct(jsAll.vs.preferred) : "—", sys.id === J.reference ? "every other system is compared with it" : null),
      speedTile);

    // Judge by text type.
    const jrows = [["all", "Both types"], ["sentence", "Sentences"], ["passage", "Passages"]].filter(([k]) => js[k]).map(([k, label]) => {
      const e = js[k], vs = e.vs, ef = e.ef;
      const n = vs && ef && vs.n !== ef.n ? `${vs.n} / ${ef.n}` : String((vs || ef || {}).n ?? "—");
      return h("tr", null, h("th", { scope: "row" }, label),
        h("td", { class: "n" }, vs ? pct(vs.preferred) : sys.id === J.reference ? "baseline" : "—"),
        h("td", { class: "n" }, vs ? `${vs.wins}–${vs.losses}` : "—"),
        h("td", { class: "n" }, vs ? String(vs.ties) : "—"),
        h("td", { class: "n" }, vs && vs.identical != null ? String(vs.identical) : "—"),
        h("td", { class: "n" }, vs ? [signed(vs.net, 3), vs.net95 ? [" ", h("span", { class: "ci" }, `[${signed(vs.net95[0], 3)}, ${signed(vs.net95[1], 3)}]`)] : null] : "—"),
        h("td", { class: "n" }, ef ? [pct(ef.value), ef.ci ? [" ", h("span", { class: "ci" }, `[${pct(ef.ci[0])}, ${pct(ef.ci[1])}]`)] : null] : "—"),
        h("td", { class: "n" }, n));
    });
    const judgeTable = jrows.length ? h("div", { class: "judge-block" }, h("h2", null, `vs ${REF}`),
      tableWrap("Judge results by text type", h("table", { class: "compact" },
        h("caption", null, `Judge: ${J.model_name}`),
        h("thead", null, h("tr", null, ["", "Preferred", "Won–lost", "Ties", "Identical", "Net [95% CI]", "Error-free [95% CI]", "n"].map((t, i) => h("th", { scope: "col", class: i ? "n" : null, title: i === 1 ? "Share of non-tied items" : null }, t)))),
        h("tbody", null, jrows)))) : null;

    // By direction; the n columns only when some direction is incomplete.
    const sCells = D.directions.map((d) => cell(sys.id, "s", d)), pCells = D.directions.map((d) => cell(sys.id, "p", d));
    const sameAttempts = (cs) => cs.every((x) => x && x[4] === x[6] && x[6] === cs[0][6]);
    const complete = sameAttempts(sCells) && sameAttempts(pCells);
    const metricsHead = complete ? ["COMET-22", "MetricX-24", "chrF++"] : ["COMET-22", "MetricX-24", "chrF++", "n"];
    const ARROW = { "COMET-22": "↑", "MetricX-24": "↓", "chrF++": "↑" };
    const headCell = (t, i) => h("th", { scope: "col", class: "n" + (i % metricsHead.length === metricsHead.length - 1 ? " group-end" : ""), title: t === "n" ? "Scored of attempted" : null },
      t, ARROW[t] ? h("span", { class: "arr", "aria-hidden": "true" }, ARROW[t]) : null);
    const trs = D.directions.map((d, i) => {
      const s = sCells[i], p = pCells[i];
      const c = (x) => (x ? [h("td", { class: "n" }, fx(x[0], 4)), h("td", { class: "n" }, fx(x[2], 3)), h("td", { class: "n" + (complete ? " group-end" : "") }, fx(x[1], 2)), complete ? null : h("td", { class: "n group-end" }, `${x[4]}/${x[6]}`)]
        : metricsHead.map((_, j) => h("td", { class: "n na" + (j === metricsHead.length - 1 ? " group-end" : "") }, "—")));
      return h("tr", null, h("th", { scope: "row", class: "sys" }, dirName(d)), c(s), c(p));
    });
    const compareHref = hashFor("compare", { sys: [sys.id, "deepl-api", "hy-mt2-30b-a3b", "gpt-6.1-terra"].filter((x, i, a) => a.indexOf(x) === i).slice(0, 3).join(",") });
    return [h("p", { class: "back" }, h("a", { href: hashFor("leaderboard", { id: "" }) }, "← Leaderboard")),
      h("div", { class: "titlebar" },
        h("h1", null, markedName(sys, h("span", null, sys.name)), " ", h("span", { class: "badge-kind kbar " + sys.kind }, sys.kind === "local" ? "Local" : "Cloud")),
        h("a", { class: "btn", href: compareHref }, "Compare")),
      tiles,
      h("h2", null, "By direction"),
      tableWrap("Scores by direction", h("table", { class: "bydir" },
        h("thead", null, h("tr", null, h("th", { scope: "col", class: "sys", rowspan: "2" }, "Direction"),
          h("th", { scope: "colgroup", colspan: String(metricsHead.length), class: "n group-end" }, complete ? "Sentences" : "Sentences (200)"),
          h("th", { scope: "colgroup", colspan: String(metricsHead.length), class: "n group-end" }, complete ? "Passages" : "Passages (20)")),
          h("tr", null, [...metricsHead, ...metricsHead].map(headCell))),
        h("tbody", null, trs))),
      h("div", { class: "sysmeta" },
        h("div", null, h("h2", null, "Setup"), dl, h("p", { class: "note" }, h("a", { href: doc("configs/systems.json") }, "Registry entry"))),
        judgeTable)];
  }

  // ---------------------------------------------------------------------------------------------
  // Frame

  function render() {
    hideTip();
    jobToken++;
    const active = document.activeElement;
    const focusKey = nextFocus || (active && app.contains(active) ? active.getAttribute("data-k") : null);
    nextFocus = null;
    for (const d of app.querySelectorAll("details.pop")) { if (d.open) openMenus.add(d.dataset.menu); else openMenus.delete(d.dataset.menu); }
    for (const a of document.querySelectorAll("#views a")) {
      const target = a.dataset.view;
      a.setAttribute("href", hashFor(target));
      // System pages and Compare (opened from a system page) sit under the leaderboard.
      if (target === view || (["system", "compare"].includes(view) && target === "leaderboard")) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    }
    const fn = { leaderboard: viewLeaderboard, compare: viewCompare, tradeoffs: viewTradeoffs, languages: viewLanguages, metrics: viewMetrics, system: viewSystem }[view];
    const section = h("section", { class: "view view-" + view }, fn());
    app.replaceChildren(section);
    if (focusKey) {
      const el = app.querySelector(`[data-k="${CSS.escape(focusKey)}"]`);
      if (el) el.focus({ preventScroll: true });
    }
    document.title = (view === "leaderboard" ? "" : (view === "system" ? (BY[st.id] ? BY[st.id].name : "System") : TITLES[view]) + " · ") + "Translate Bench";
  }
  // After a navigation: to the requested section, or to the top.
  function settle() {
    const target = scrollTarget;
    scrollTarget = null;
    if (!target) { window.scrollTo(0, 0); return; }
    // After the charts above the section are drawn.
    requestAnimationFrame(() => requestAnimationFrame(() => {
      const el = document.getElementById(target);
      if (el) { el.scrollIntoView(); el.focus({ preventScroll: true }); }
    }));
  }

  function theme() {
    const btn = document.getElementById("theme");
    const label = () => {
      const t = document.documentElement.dataset.theme || "auto";
      btn.textContent = "Theme: " + t;
      btn.setAttribute("aria-label", "Colour theme: " + (t === "auto" ? "follows the system" : t) + ". Change");
    };
    btn.addEventListener("click", () => {
      const cur = document.documentElement.dataset.theme || "auto";
      const next = cur === "auto" ? "light" : cur === "light" ? "dark" : "auto";
      if (next === "auto") delete document.documentElement.dataset.theme;
      else document.documentElement.dataset.theme = next;
      try { if (next === "auto") localStorage.removeItem("tb-theme"); else localStorage.setItem("tb-theme", next); } catch (e) { /* storage unavailable */ }
      label();
    });
    label();
  }

  // Open menus close on a press elsewhere (before any redraw it causes) or on Escape.
  document.addEventListener("pointerdown", (e) => {
    for (const d of app.querySelectorAll("details.pop[open]")) if (!d.contains(e.target)) d.open = false;
  }, true);
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    for (const d of app.querySelectorAll("details.pop[open]")) {
      d.open = false;
      if (d.contains(document.activeElement)) d.querySelector("summary").focus();
    }
  });
  // The skip link moves focus without changing the view in the hash.
  const skip = document.querySelector(".skip");
  if (skip) skip.addEventListener("click", (e) => { e.preventDefault(); document.getElementById("main").focus(); });

  let lastWidth = window.innerWidth, lastNarrow = NARROW();
  window.addEventListener("resize", () => {
    const narrow = NARROW();
    if (narrow !== lastNarrow && view === "leaderboard") { lastNarrow = narrow; lastWidth = window.innerWidth; render(); return; }
    lastNarrow = narrow;
    if (Math.abs(window.innerWidth - lastWidth) < 40) return;
    lastWidth = window.innerWidth;
    clearTimeout(window.__tbResize);
    window.__tbResize = setTimeout(() => { if (["tradeoffs", "metrics", "compare"].includes(view)) render(); }, 150);
  });
  window.addEventListener("hashchange", () => {
    for (const d of app.querySelectorAll("details.pop")) d.open = false;
    if (readHash()) { render(); settle(); }
  });
  theme();
  if (readHash()) {
    render();
    if (scrollTarget) settle();
  }
})();
