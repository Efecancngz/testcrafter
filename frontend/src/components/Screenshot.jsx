import { useState, useEffect } from "react";
import { fetchScreenshotUrl } from "../api";

export default function Screenshot({ path, stepIndex }) {
  const [src, setSrc] = useState(null);

  useEffect(() => {
    let objectUrl;
    let cancelled = false;
    fetchScreenshotUrl(path).then((url) => {
      if (cancelled) {
        URL.revokeObjectURL(url);
        return;
      }
      objectUrl = url;
      setSrc(url);
    }).catch(() => {});
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [path]);

  if (!src) return null;
  return <img src={src} alt={`Step ${stepIndex} screenshot`} loading="lazy" className="max-w-[200px] rounded-md border border-border" />;
}
