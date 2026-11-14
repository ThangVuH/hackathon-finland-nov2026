/** Browser-only: loads a drawing and re-encodes it at a bounded size for AI analysis (aspect ratio preserved, so 0-1000 coordinates still map 1:1). */
export interface PreparedImage {
  dataUrl: string;
  width: number;
  height: number;
}

const MAX_SIDE = 2048;

export function prepareImageForAnalysis(src: string): Promise<PreparedImage> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    if (!src.startsWith("data:")) img.crossOrigin = "anonymous";
    img.onload = () => {
      const scale = Math.min(1, MAX_SIDE / Math.max(img.naturalWidth, img.naturalHeight));
      const width = Math.max(1, Math.round(img.naturalWidth * scale));
      const height = Math.max(1, Math.round(img.naturalHeight * scale));
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext("2d");
      if (!ctx) return reject(new Error("Canvas unavailable"));
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, width, height);
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = "high";
      ctx.drawImage(img, 0, 0, width, height);
      resolve({ dataUrl: canvas.toDataURL("image/jpeg", 0.92), width, height });
    };
    img.onerror = () => reject(new Error("Could not read this image"));
    img.src = src;
  });
}

export const ACCEPTED_TYPES = ["image/png", "image/jpeg", "image/webp"];
