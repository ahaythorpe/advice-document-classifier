# Advice Document Filing: web demo (React)

React 18 + Vite. Builds to ONE self-contained HTML file with a `__DATA__`
placeholder, so build_web.py keeps its single string replace.

    npm install
    npm run build        # -> dist/index.html (template, contains __DATA__)

In build_web.py, read web-react/dist/index.html as PAGE and keep:

    page = PAGE.replace("__DATA__", json.dumps(payload, ensure_ascii=False))

Local preview with the sample data:

    npm run preview:sample   # writes dist/demo.html with sample-data.json filled in

No external requests at runtime; works under the existing vercel.json CSP
(inline scripts and styles only).
