/* Оболочка сайта в кэше: страница открывается и без сети.
   Данные живут в localStorage браузера и кэш их не трогает. */
var CACHE = "masterskaya-v2";
var SHELL = ["./", "./index.html", "./config.js", "./vendor/supabase.js",
             "./manifest.webmanifest", "./icon.svg", "./icon-192.png", "./icon-512.png"];

self.addEventListener("install", function(e){
  e.waitUntil(caches.open(CACHE).then(function(c){ return c.addAll(SHELL); }).then(function(){ return self.skipWaiting(); }));
});

self.addEventListener("activate", function(e){
  e.waitUntil(caches.keys().then(function(keys){
    return Promise.all(keys.map(function(k){ return k === CACHE ? null : caches.delete(k); }));
  }).then(function(){ return self.clients.claim(); }));
});

self.addEventListener("fetch", function(e){
  var req = e.request;
  if(req.method !== "GET") return;
  var url = new URL(req.url);
  if(url.origin !== location.origin) return;
  /* общее состояние и настройки подключения всегда берём из сети */
  if(url.pathname.indexOf("/data/") > -1) return;
  if(/config\.js$/.test(url.pathname)){
    e.respondWith(fetch(req).catch(function(){ return caches.match(req); }));
    return;
  }

  /* HTML — сначала сеть (чтобы приходили обновления), кэш как запасной путь */
  if(req.mode === "navigate" || (req.headers.get("accept") || "").indexOf("text/html") > -1){
    e.respondWith(
      fetch(req).then(function(res){
        var copy = res.clone();
        caches.open(CACHE).then(function(c){ c.put("./index.html", copy); });
        return res;
      }).catch(function(){
        return caches.match("./index.html").then(function(r){ return r || Response.error(); });
      })
    );
    return;
  }

  /* остальное — сначала кэш */
  e.respondWith(caches.match(req).then(function(hit){
    return hit || fetch(req).then(function(res){
      if(res.ok){ var copy = res.clone(); caches.open(CACHE).then(function(c){ c.put(req, copy); }); }
      return res;
    });
  }));
});
