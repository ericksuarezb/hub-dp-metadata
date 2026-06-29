const puppeteer = require("puppeteer");
const { setTimeout } = require("node:timers/promises");

function usage() {
  console.log(
    "usage: save-report.js --url redash_url --output report.pdf " +
      "[--delay seconds] [--timeout seconds] " +
      "[--param value] [--param value]",
  );
  process.exit(1);
}

let redashUrl;
let outputFile;
let renderDelay = 0.5;
let navigationTimeout = 300;
let screenshot = false;
const params = {};

for (let i = 2; i < process.argv.length; i++) {
  switch (process.argv[i]) {
    case "--url":
      redashUrl = process.argv[++i];
      break;
    case "--delay":
      renderDelay = parseFloat(process.argv[++i]);
      break;
    case "--timeout":
      navigationTimeout = parseInt(process.argv[++i]);
      break;
    case "--output":
      outputFile = process.argv[++i];
      break;
    case "--param": {
      const kv = process.argv[++i].split("=", 2);
      params[kv[0]] = kv[1];
      break;
    }
    case "--screenshot":
      screenshot = true;
      break;
    default:
      usage();
  }
}
if (!redashUrl || !outputFile) {
  usage();
}

function replaceParams(pageUrl, currentParams) {
  const url = new URL(pageUrl);
  const qs = url.searchParams;

  for (const [key, value] of Object.entries(currentParams)) {
    qs.set("p_" + key, value);
  }
  url.search = qs.toString();
  return url.toString();
}

(async () => {
  const browser = await puppeteer.launch({
    defaultViewport: { width: 1200, height: 1200 },
    args: ["--ignore-certificate-errors", "--no-sandbox"],
    headless: "new",
  });
  const page = await browser.newPage();

  page.setDefaultNavigationTimeout(navigationTimeout * 1000);
  page.setDefaultTimeout(navigationTimeout * 1000);

  await page.goto(redashUrl, {
    waitUntil: "networkidle0",
  });

  if (params) {
    await page.goto(replaceParams(page.url(), params), {
      waitUntil: "networkidle0",
    });
  }

  await page.evaluate(
    (currentParams, isScreenshot) => {
      function removeElementsByClass(className) {
        const elements = document.getElementsByClassName(className);
        while (elements.length > 0) {
          elements[0].parentNode.removeChild(elements[0]);
        }
      }

      function formatDate(date) {
        return date.toLocaleDateString("en", {
          year: "numeric",
          day: "numeric",
          month: "long",
        });
      }

      removeElementsByClass("ant-input-number-handler-wrap");
      removeElementsByClass("ant-select-arrow");
      removeElementsByClass("hoverlayer");
      removeElementsByClass("zoomlayer");
      removeElementsByClass("modebar-container");
      removeElementsByClass("ant-table-column-sorter");
      removeElementsByClass("visible-print");

      const footer = document.getElementById("footer");
      if (footer) {
        footer.innerHTML = "";
      }

      if (!isScreenshot) {
        const style = document.createElement("style");
        style.innerHTML = `
      @page {
          margin: 1cm;
      }
      div.body-container {
          border: 1pt solid #333;
          border-radius: 2pt;
      }
      `;
        document.head.appendChild(style);
      }

      const todayDiv = document.createElement("div");
      todayDiv.className = "page-header-wrapper";
      todayDiv.innerText = "Generated on " + formatDate(new Date());

      for (const param in currentParams) {
        let paramMatches = 0;
        for (const parameterBlock of document.getElementsByClassName("parameter-block")) {
          if (parameterBlock.getAttribute("data-test") == `ParameterBlock-${param}`) {
            const parameterInput = parameterBlock.getElementsByClassName("parameter-input");
            paramMatches++;
            parameterInput[0].innerHTML = `
          <input class="ant-input" aria-label="Parameter text value"
                 data-test="TextParamInput" type="text" value="${currentParams[param]}">
          `;
          }
        }
        if (paramMatches == 0) {
          throw Error(`no match found for parameter "${param}"`);
        }
      }

      const applyButton = document.getElementsByClassName("parameter-apply-button")[0];
      if (applyButton) {
        applyButton.remove();
      }

      const headerDiv = document.getElementsByClassName("page-header-wrapper")[0];
      if (headerDiv) {
        headerDiv.insertAdjacentElement("afterend", todayDiv);
      }
    },
    params,
    screenshot,
  );

  await page.waitForSelector(".spinner", { hidden: true });

  if (renderDelay) {
    await setTimeout(renderDelay * 1000);
  }

  if (screenshot) {
    const layoutElement = await page.$("div > .react-grid-layout");
    await page.screenshot({
      path: outputFile,
      clip: await layoutElement.boundingBox(),
      captureBeyondViewport: false,
    });
  } else {
    await page.pdf({
      path: outputFile,
      width: "11in",
      height: "17in",
      displayHeaderFooter: false,
      scale: 0.8,
    });
  }

  await browser.close();
})();
