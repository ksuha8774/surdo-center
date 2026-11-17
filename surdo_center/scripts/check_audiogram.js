const assert = require("node:assert/strict");
const audiogram = require("../static/js/audiogram.js");

assert.equal(audiogram.frequencyPosition(125, 0, 100), 0);
assert.equal(Math.round(audiogram.frequencyPosition(8000, 0, 100)), 100);
assert.equal(audiogram.levelPosition(-10, 20, 140), 20);
assert.equal(audiogram.levelPosition(130, 20, 140), 160);

const segments = audiogram.splitSegments([
  { frequency_hz: 500, threshold_db_hl: 10, no_response: false },
  { frequency_hz: 1000, threshold_db_hl: null, no_response: true },
  { frequency_hz: 2000, threshold_db_hl: 20, no_response: false },
  { frequency_hz: 3000, threshold_db_hl: 25, no_response: false },
]);
assert.equal(segments.length, 2);
assert.equal(segments[0].length, 1);
assert.equal(segments[1].length, 2);

assert.equal(audiogram.seriesKey({ ear: "right", conduction_type: "air", masked: false }), "right_air_plain");
console.log("Audiogram helpers: OK");
