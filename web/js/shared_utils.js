// code based on mtb nodes by Mel Massadian https://github.com/melMass/comfy_mtb/ and KJNodes
export function loadScript(
  FILE_URL,
  async = true,
  type = 'text/javascript',
) {
  return new Promise((resolve, reject) => {
    try {
      // Check if the script already exists
      const existingScript = document.querySelector(`script[src="${FILE_URL}"]`)
      if (existingScript) {
        resolve({ status: true, message: 'Script already loaded' })
        return
      }

      const scriptEle = document.createElement('script')
      scriptEle.type = type
      scriptEle.async = async
      scriptEle.src = FILE_URL

      scriptEle.addEventListener('load', (ev) => {
        resolve({ status: true })
      })

      scriptEle.addEventListener('error', (ev) => {
        reject({
          status: false,
          message: `Failed to load the script ${FILE_URL}`,
        })
      })

      document.body.appendChild(scriptEle)
    } catch (error) {
      reject(error)
    }
  })
}

export function getResolver(timeout = 5000) {
    const resolver = {};
    resolver.id = generateId(8);
    resolver.completed = false;
    resolver.resolved = false;
    resolver.rejected = false;
    resolver.promise = new Promise((resolve, reject) => {
        resolver.reject = () => {
            resolver.completed = true;
            resolver.rejected = true;
            reject();
        };
        resolver.resolve = (data) => {
            resolver.completed = true;
            resolver.resolved = true;
            resolve(data);
        };
    });
    resolver.timeout = setTimeout(() => {
        if (!resolver.completed) {
            resolver.reject();
        }
    }, timeout);
    return resolver;
}
export function wait(ms = 16, value) {
    if (ms === 16) {
        return new Promise((resolve) => {
            requestAnimationFrame(resolve);
        });
    }
    return new Promise((resolve) => {
        setTimeout(() => {
            resolve(value);
        }, ms);
    });
}
function dec2hex(dec) {
    return dec.toString(16).padStart(2, "0");
}
export function generateId(length) {
    const arr = new Uint8Array(length / 2);
    crypto.getRandomValues(arr);
    return Array.from(arr, dec2hex).join("");
}
export function getObjectValue(obj, objKey, def) {
    if (!obj || !objKey)
        return def;
    const keys = objKey.split(".");
    const key = keys.shift();
    const found = obj[key];
    if (keys.length) {
        return getObjectValue(found, keys.join("."), def);
    }
    return found;
}
export function setObjectValue(obj, objKey, value, createMissingObjects = true) {
    if (!obj || !objKey)
        return obj;
    const keys = objKey.split(".");
    const key = keys.shift();
    if (obj[key] === undefined) {
        if (!createMissingObjects) {
            return;
        }
        obj[key] = {};
    }
    if (!keys.length) {
        obj[key] = value;
    }
    else {
        if (typeof obj[key] != "object") {
            obj[key] = {};
        }
        setObjectValue(obj[key], keys.join("."), value, createMissingObjects);
    }
    return obj;
}
export function moveArrayItem(arr, itemOrFrom, to) {
    const from = typeof itemOrFrom === "number" ? itemOrFrom : arr.indexOf(itemOrFrom);
    arr.splice(to, 0, arr.splice(from, 1)[0]);
}
export function removeArrayItem(arr, itemOrIndex) {
    const index = typeof itemOrIndex === "number" ? itemOrIndex : arr.indexOf(itemOrIndex);
    arr.splice(index, 1);
}
export function injectCss(href) {
    if (document.querySelector(`link[href^="${href}"]`)) {
        return Promise.resolve();
    }
    return new Promise((resolve) => {
        const link = document.createElement('link');
        link.setAttribute('rel', "stylesheet");
        link.setAttribute('type', "text/css");
        const timeout = setTimeout(resolve, 1000);
        link.addEventListener("load", (e) => {
            clearInterval(timeout);
            resolve();
        });
        link.href = href;
        document.head.appendChild(link);
    });
}
export function injectJs(href) {
    if (document.querySelector(`script[src^="${href}"]`)) {
        return Promise.resolve();
    }
    return new Promise((resolve) => {
        const script = document.createElement('script');
        script.setAttribute('type', "text/javascript");
        const timeout = setTimeout(resolve, 1000);
        script.addEventListener("load", (e) => {
            clearInterval(timeout);
            resolve();
        });
        script.src = href;
        document.head.appendChild(script);
    });
}
