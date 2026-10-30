import assert from "node:assert/strict";
import test from "node:test";
import {readPackage, simulate} from "../simulation.mjs";

// A tiny 0 -> 1 -> 2 graph. Its FMC1 CSR stores the REVERSED edges.
function sample() {
  const metadata = new TextEncoder().encode(JSON.stringify({
    format_version: 1, execution_id: 7,
    categories: ["health", "food"], threshold_minutes: 15
  }));
  const start = Math.ceil((20 + metadata.length) / 8) * 8;
  const bytes = new ArrayBuffer(start + 3 * (24 + 8 * 2) + 4 * 4 + 12 * 2);
  const view = new DataView(bytes);
  for (let i=0; i<4; i++) view.setUint8(i, "FMC1".charCodeAt(i));
  view.setUint32(4, metadata.length, true);
  view.setUint32(8, 3, true);
  view.setUint32(12, 2, true);
  view.setUint32(16, 2, true);
  new Uint8Array(bytes).set(metadata, 20);
  let p = start;
  function doubles(data) {for(const value of data){view.setFloat64(p,value,true);p+=8;}}
  function ints(data) {for(const value of data){view.setUint32(p,value,true);p+=4;}}
  doubles([0,0, 0.005,0, 0.01,0]);
  doubles([50,0,50]);
  doubles([0,2400, 1200,1200, 2400,0]);
  ints([0,0,1,2]); ints([0,1]); doubles([1200,1200]);
  return readPackage(bytes);
}
test("parse FMC1 reverse CSR", () => {
  assert.deepEqual([...sample().offsets],[0,0,1,2]);
});
test("client-side incremental routing changes only affected categories", () => {
  const pkg = sample();
  const before = [...pkg.baseline];
  const result = simulate(pkg, [{name:"UBS",category:"health",longitude:0.01,latitude:0}]);
  assert.equal(result.baseline.population.overall_coverage_percentage,0);
  assert.equal(result.simulated.population.overall_coverage_percentage,50);
  assert.equal(result.simulated.population.categories.health.coverage_percentage,100);
  assert.equal(result.delta.population.overall_coverage,50);
  assert.equal(result.simulated.population.categories.health.mean_travel_time_minutes,0);
  assert.deepEqual([...pkg.baseline], before);
});
test("multiple categories combine correctly", () => {
  const result = simulate(sample(),[
    {category:"health",longitude:0.01,latitude:0},
    {category:"food",longitude:0,latitude:0}
  ]);
  assert.equal(result.simulated.population.overall_coverage_percentage,100);
});
test("invalid points and unknown categories are refused", () => {
  const pkg=sample();
  assert.throws(()=>simulate(pkg,[{category:"culture",longitude:0,latitude:0}]),/not analyzed/);
  assert.throws(()=>simulate(pkg,[{category:"health",longitude:1,latitude:1}]),/too far/);
});
