 // Usage: node client/simulate-cli.mjs <package.fmc.gz|HTTPS_URL> <scenario.geojson>
 import { readFileSync } from "node:fs";
 import { gunzipSync } from "node:zlib";
 import { readPackage, simulate } from "./simulation.mjs";

 async function load(source) {
   if (/^https:\/\//.test(source)) {
     const headers = process.env.API_KEY ? { "X-API-Key": process.env.API_KEY } : {};
     const response = await fetch(source, { headers });
     if (!response.ok) throw Error("Package request failed: HTTP " + response.status);
     // HTTP clients automatically decode Content-Encoding: gzip.
     return new Uint8Array(await response.arrayBuffer());
   }
   const bytes = readFileSync(source);
   return source.endsWith(".gz") ? gunzipSync(bytes) : bytes;
 }

 const [packagePath, scenarioPath] = process.argv.slice(2);
 if (!packagePath || !scenarioPath) {
   console.error("Usage: node client/simulate-cli.mjs <package.fmc.gz|HTTPS_URL> <scenario.geojson>");
   process.exitCode = 2;
 } else {
   try {
     const data = JSON.parse(readFileSync(scenarioPath, "utf8"));
     if (data.type !== "FeatureCollection" || !Array.isArray(data.features)) {
       throw Error("Expected GeoJSON FeatureCollection");
     }
     const services = data.features.map((feature) => {
       if (feature.geometry?.type !== "Point" || feature.geometry.coordinates?.length !== 2) {
         throw Error("Scenario features must be GeoJSON Points");
       }
       return {
         category: feature.properties?.category,
         name: feature.properties?.name ?? null,
         longitude: feature.geometry.coordinates[0],
         latitude: feature.geometry.coordinates[1],
       };
     });
     const pkg = readPackage(await load(packagePath));
     console.log(JSON.stringify(simulate(pkg, services), null, 2));
   } catch (error) {
     console.error(error.message);
     process.exitCode = 1;
   }
 }
