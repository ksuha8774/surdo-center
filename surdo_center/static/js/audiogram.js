(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.YunaAudiogram = api;
})(typeof window !== "undefined" ? window : null, function () {
  "use strict";

  const FREQUENCIES = [125, 250, 500, 750, 1000, 1500, 2000, 3000, 4000, 6000, 8000];
  const DB_MIN = -10;
  const DB_MAX = 130;
  const SVG_NS = "http://www.w3.org/2000/svg";
  const SERIES = {
    right_air_plain: { color: "#dc343f", symbol: "O", dash: "", label: "Правое, воздушная" },
    right_air_masked: { color: "#dc343f", symbol: "△", dash: "7 4", label: "Правое, воздушная с маскировкой" },
    left_air_plain: { color: "#1769d2", symbol: "X", dash: "", label: "Левое, воздушная" },
    left_air_masked: { color: "#1769d2", symbol: "□", dash: "7 4", label: "Левое, воздушная с маскировкой" },
    right_bone_plain: { color: "#dc343f", symbol: "<", dash: "3 4", label: "Правое, костная" },
    right_bone_masked: { color: "#dc343f", symbol: "[", dash: "3 4", label: "Правое, костная с маскировкой" },
    left_bone_plain: { color: "#1769d2", symbol: ">", dash: "3 4", label: "Левое, костная" },
    left_bone_masked: { color: "#1769d2", symbol: "]", dash: "3 4", label: "Левое, костная с маскировкой" },
  };

  function seriesKey(item) {
    return `${item.ear}_${item.conduction_type}_${item.masked ? "masked" : "plain"}`;
  }

  function frequencyPosition(frequency, left, width) {
    const start = Math.log2(FREQUENCIES[0]);
    const end = Math.log2(FREQUENCIES[FREQUENCIES.length - 1]);
    return left + ((Math.log2(Number(frequency)) - start) / (end - start)) * width;
  }

  function levelPosition(level, top, height) {
    return top + ((Number(level) - DB_MIN) / (DB_MAX - DB_MIN)) * height;
  }

  function splitSegments(items) {
    const ordered = [...items].sort((a, b) => a.frequency_hz - b.frequency_hz);
    const segments = [];
    let current = [];
    let previousIndex = null;
    ordered.forEach((item) => {
      const index = FREQUENCIES.indexOf(Number(item.frequency_hz));
      const usable = index >= 0 && !item.no_response && item.threshold_db_hl !== null && item.threshold_db_hl !== undefined;
      if (!usable || (previousIndex !== null && index !== previousIndex + 1)) {
        if (current.length) segments.push(current);
        current = [];
      }
      if (usable) {
        current.push(item);
        previousIndex = index;
      } else {
        previousIndex = null;
      }
    });
    if (current.length) segments.push(current);
    return segments;
  }

  function svgNode(tag, attributes, text) {
    const node = document.createElementNS(SVG_NS, tag);
    Object.entries(attributes || {}).forEach(([name, value]) => node.setAttribute(name, String(value)));
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function visible(item, filters) {
    const earVisible = filters.ear === "both" || filters.ear === item.ear;
    const conductionVisible = filters.conduction === "both" || filters.conduction === item.conduction_type;
    return earVisible && conductionVisible;
  }

  function draw(container, measurements, filters) {
    if (typeof document === "undefined") return;
    const width = 980;
    const height = 560;
    const margin = { left: 72, right: 26, top: 34, bottom: 58 };
    const plotWidth = width - margin.left - margin.right;
    const plotHeight = height - margin.top - margin.bottom;
    const svg = svgNode("svg", {
      viewBox: `0 0 ${width} ${height}`,
      role: "img",
      "aria-label": "Аудиограмма",
      class: "audiogram-svg",
    });

    svg.appendChild(svgNode("rect", {
      x: margin.left, y: margin.top, width: plotWidth, height: plotHeight,
      rx: 8, fill: "#fff", stroke: "#a9c5da",
    }));

    for (let db = DB_MIN; db <= DB_MAX; db += 10) {
      const y = levelPosition(db, margin.top, plotHeight);
      svg.appendChild(svgNode("line", {
        x1: margin.left, y1: y, x2: width - margin.right, y2: y,
        stroke: db === 0 ? "#7898ae" : "#dbe8f1", "stroke-width": db === 0 ? 1.5 : 1,
      }));
      svg.appendChild(svgNode("text", {
        x: margin.left - 12, y: y + 4, "text-anchor": "end", class: "audiogram-axis-label",
      }, db));
    }

    FREQUENCIES.forEach((frequency) => {
      const x = frequencyPosition(frequency, margin.left, plotWidth);
      svg.appendChild(svgNode("line", {
        x1: x, y1: margin.top, x2: x, y2: height - margin.bottom, stroke: "#e2edf4", "stroke-width": 1,
      }));
      svg.appendChild(svgNode("text", {
        x, y: height - margin.bottom + 25, "text-anchor": "middle", class: "audiogram-axis-label",
      }, frequency >= 1000 ? `${frequency / 1000}k` : frequency));
    });

    svg.appendChild(svgNode("text", {
      x: margin.left + plotWidth / 2, y: height - 12, "text-anchor": "middle", class: "audiogram-axis-title",
    }, "Частота, Гц"));
    svg.appendChild(svgNode("text", {
      x: 17, y: margin.top + plotHeight / 2, transform: `rotate(-90 17 ${margin.top + plotHeight / 2})`,
      "text-anchor": "middle", class: "audiogram-axis-title",
    }, "Уровень слуха, дБ HL"));

    const groups = {};
    measurements.filter((item) => visible(item, filters)).forEach((item) => {
      const key = seriesKey(item);
      (groups[key] ||= []).push(item);
    });

    Object.entries(groups).forEach(([key, items]) => {
      const style = SERIES[key];
      if (!style) return;
      splitSegments(items).forEach((segment) => {
        if (segment.length < 2) return;
        const points = segment.map((item) => {
          const x = frequencyPosition(item.frequency_hz, margin.left, plotWidth);
          const y = levelPosition(item.threshold_db_hl, margin.top, plotHeight);
          return `${x},${y}`;
        }).join(" ");
        svg.appendChild(svgNode("polyline", {
          points, fill: "none", stroke: style.color, "stroke-width": 2,
          "stroke-dasharray": style.dash, "stroke-linejoin": "round",
        }));
      });

      items.forEach((item) => {
        const value = item.no_response ? item.no_response_level_db_hl : item.threshold_db_hl;
        if (value === null || value === undefined) return;
        const x = frequencyPosition(item.frequency_hz, margin.left, plotWidth);
        const y = levelPosition(value, margin.top, plotHeight);
        const group = svgNode("g", { class: "audiogram-point", tabindex: "0" });
        group.appendChild(svgNode("title", {}, `${style.label}: ${item.frequency_hz} Гц, ${value} дБ HL${item.no_response ? ", ответа нет" : ""}`));
        group.appendChild(svgNode("text", {
          x, y: y + 6, "text-anchor": "middle", fill: style.color,
          "font-size": 21, "font-weight": 800,
        }, style.symbol));
        if (item.no_response) {
          group.appendChild(svgNode("line", {
            x1: x + 7, y1: y + 5, x2: x + 7, y2: Math.min(y + 20, height - margin.bottom),
            stroke: style.color, "stroke-width": 2,
          }));
          group.appendChild(svgNode("path", {
            d: `M ${x + 2} ${Math.min(y + 15, height - margin.bottom)} L ${x + 7} ${Math.min(y + 21, height - margin.bottom)} L ${x + 12} ${Math.min(y + 15, height - margin.bottom)}`,
            fill: "none", stroke: style.color, "stroke-width": 2,
          }));
        }
        svg.appendChild(group);
      });
    });

    container.replaceChildren(svg);
    return svg;
  }

  function readMeasurementsFromForm(form) {
    if (!form) return null;
    const result = [];
    const pattern = /^(right|left)_(air|bone)_(plain|masked)_(\d+)_(threshold|no_response|level)$/;
    const grouped = {};
    form.querySelectorAll("input[name]").forEach((input) => {
      const match = input.name.match(pattern);
      if (!match) return;
      const [, ear, conduction, masking, frequency, field] = match;
      const key = `${ear}_${conduction}_${masking}_${frequency}`;
      grouped[key] ||= { ear, conduction_type: conduction, masked: masking === "masked", frequency_hz: Number(frequency) };
      grouped[key][field] = input.type === "checkbox" ? input.checked : input.value;
    });
    Object.values(grouped).forEach((item) => {
      const threshold = item.threshold === "" ? null : Number(item.threshold);
      const level = item.level === "" ? null : Number(item.level);
      if (threshold === null && !item.no_response && level === null) return;
      result.push({
        ear: item.ear,
        conduction_type: item.conduction_type,
        frequency_hz: item.frequency_hz,
        threshold_db_hl: item.no_response ? null : threshold,
        masked: item.masked,
        no_response: Boolean(item.no_response),
        no_response_level_db_hl: item.no_response ? level : null,
      });
    });
    return result;
  }

  function init() {
    if (typeof document === "undefined") return;
    document.querySelectorAll("[data-audiogram]").forEach((root) => {
      const canvas = root.querySelector("[data-audiogram-canvas]");
      const dataNode = document.getElementById(root.dataset.audiogramData || "audiogram-data");
      let measurements = dataNode ? JSON.parse(dataNode.textContent || "[]") : [];
      const filters = { ear: "both", conduction: "both" };
      const render = () => draw(canvas, measurements, filters);
      root.querySelectorAll("[data-audiogram-ear]").forEach((button) => button.addEventListener("click", () => {
        filters.ear = button.dataset.audiogramEar;
        root.querySelectorAll("[data-audiogram-ear]").forEach((item) => item.classList.toggle("active", item === button));
        render();
      }));
      root.querySelectorAll("[data-audiogram-conduction]").forEach((button) => button.addEventListener("click", () => {
        filters.conduction = button.dataset.audiogramConduction;
        root.querySelectorAll("[data-audiogram-conduction]").forEach((item) => item.classList.toggle("active", item === button));
        render();
      }));
      const form = document.querySelector("[data-audiometry-form]");
      if (form) {
        const formMeasurements = readMeasurementsFromForm(form);
        if (formMeasurements && formMeasurements.length) measurements = formMeasurements;
        form.addEventListener("input", () => {
          measurements = readMeasurementsFromForm(form) || measurements;
          render();
        });
      }
      root.querySelector("[data-audiogram-print]")?.addEventListener("click", () => window.print());
      root.querySelector("[data-audiogram-download]")?.addEventListener("click", () => {
        const svg = canvas.querySelector("svg");
        if (!svg) return;
        const blob = new Blob([new XMLSerializer().serializeToString(svg)], { type: "image/svg+xml;charset=utf-8" });
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = `audiogram-${root.dataset.examId || "exam"}.svg`;
        link.click();
        URL.revokeObjectURL(link.href);
      });
      render();
    });
  }

  if (typeof document !== "undefined") {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
    else init();
  }

  return { FREQUENCIES, SERIES, frequencyPosition, levelPosition, splitSegments, seriesKey };
});
