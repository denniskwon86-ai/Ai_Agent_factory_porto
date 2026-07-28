/* SVG 다이어그램을 Word 호환용 PNG로 함께 생성한다. */
const fs = require("fs");
const path = require("path");
const { Resvg } = require("@resvg/resvg-js");

const assetDir = path.resolve(__dirname, "..", "docs", "assets");
const diagrams = ["as_is_screen_structure.svg", "as_is_system_architecture.svg"];

for (const sourceName of diagrams) {
  const sourcePath = path.join(assetDir, sourceName);
  const targetPath = path.join(assetDir, sourceName.replace(/\.svg$/i, ".png"));
  const svg = fs.readFileSync(sourcePath);
  const rendered = new Resvg(svg, {
    font: { loadSystemFonts: true, defaultFontFamily: "Malgun Gothic" },
    fitTo: { mode: "original" },
    background: "#F5F8FC",
  });
  fs.writeFileSync(targetPath, rendered.render().asPng());
  console.log(`${path.basename(targetPath)} (${fs.statSync(targetPath).size} bytes)`);
}
