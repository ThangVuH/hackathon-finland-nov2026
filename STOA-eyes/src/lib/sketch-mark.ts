/** Two marks, scored separately. A clean drafted sheet is sent as drawn. Any other sheet is complicated and can be simplified first. */

export interface InkRead {
  drafted: boolean;
  handSketch: boolean;
  complicated: boolean;
}

const EMPTY: InkRead = { drafted: false, handSketch: false, complicated: false };

export function classifyInk(gray: Uint8Array, width: number, height: number): InkRead {
  const count = width * height;
  if (count < 64 || gray.length < count) return EMPTY;
  const paper = percentile(gray, count, 0.9);
  const dark = band(gray, width, height, 40);
  const drafted = paper > 240 && dark.count > 30 && dark.std < 18 && dark.jump < 0.12;
  const loose = loosePencil(gray, width, height);
  // Thin gray on a CAD sheet is a light line, not a pencil note.
  // A sketch on a drafted sheet is a gray patch: many gray pixels sitting together.
  const handSketch = loose.count >= 36 && loose.std > 12 && (!drafted || loose.solid >= 80);
  return { drafted, handSketch, complicated: !drafted || handSketch };
}

function band(gray: Uint8Array, width: number, height: number, cut: number) {
  let count = 0;
  let sum = 0;
  let sumSq = 0;
  let pairs = 0;
  let jumps = 0;
  for (let y = 0; y < height; y++) {
    const row = y * width;
    for (let x = 0; x < width; x++) {
      const lum = gray[row + x] ?? 0;
      if (lum >= cut) continue;
      count++;
      sum += lum;
      sumSq += lum * lum;
      const prev = x > 0 ? (gray[row + x - 1] ?? 255) : 255;
      if (prev < cut) {
        pairs++;
        if (Math.abs(lum - prev) > 25) jumps++;
      }
    }
  }
  const mean = count === 0 ? 0 : sum / count;
  return {
    count,
    mean,
    std: count === 0 ? 0 : Math.sqrt(Math.max(0, sumSq / count - mean * mean)),
    jump: pairs === 0 ? 0 : jumps / pairs,
  };
}

/** Gray strokes that are not the soft edge of a black line. */
function loosePencil(gray: Uint8Array, width: number, height: number) {
  let count = 0;
  let sum = 0;
  let sumSq = 0;
  let prevLoose = false;
  let prevLum = 0;
  let pairs = 0;
  let jumps = 0;
  const dark = (index: number) => (gray[index] ?? 255) < 45;
  const mask = new Uint8Array(width * height);
  for (let y = 0; y < height; y++) {
    prevLoose = false;
    const row = y * width;
    for (let x = 0; x < width; x++) {
      const lum = gray[row + x] ?? 0;
      const besideInk =
        (x > 0 && dark(row + x - 1)) ||
        (x + 1 < width && dark(row + x + 1)) ||
        (y > 0 && dark(row - width + x)) ||
        (y + 1 < height && dark(row + width + x));
      const loose = lum >= 50 && lum <= 160 && !besideInk;
      if (loose) {
        mask[row + x] = 1;
        count++;
        sum += lum;
        sumSq += lum * lum;
        if (prevLoose) {
          pairs++;
          if (Math.abs(lum - prevLum) > 20) jumps++;
        }
      }
      prevLoose = loose;
      prevLum = lum;
    }
  }
  let solid = 0;
  for (let y = 0; y < height; y++) {
    const row = y * width;
    for (let x = 0; x < width; x++) {
      const index = row + x;
      if (!mask[index]) continue;
      let neighbors = 0;
      if (x > 0 && mask[index - 1]) neighbors++;
      if (x + 1 < width && mask[index + 1]) neighbors++;
      if (y > 0 && mask[index - width]) neighbors++;
      if (y + 1 < height && mask[index + width]) neighbors++;
      if (neighbors >= 3) solid++;
    }
  }
  const mean = count === 0 ? 0 : sum / count;
  return {
    count,
    std: count === 0 ? 0 : Math.sqrt(Math.max(0, sumSq / count - mean * mean)),
    jump: pairs === 0 ? 0 : jumps / pairs,
    solid,
  };
}

function percentile(gray: Uint8Array, count: number, p: number): number {
  const copy = Array.from(gray.subarray(0, count)).sort((a, b) => a - b);
  const index = Math.min(copy.length - 1, Math.max(0, Math.round((copy.length - 1) * p)));
  return copy[index] ?? 255;
}

/** Browser-only. A failed read leaves both marks off so the sheet still analyzes as before. */
export function detectSheetMarks(src: string): Promise<InkRead> {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      try {
        const scale = Math.min(1, 160 / Math.max(img.naturalWidth, img.naturalHeight));
        const width = Math.max(1, Math.round(img.naturalWidth * scale));
        const height = Math.max(1, Math.round(img.naturalHeight * scale));
        const canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext("2d");
        if (!ctx) return resolve(EMPTY);
        ctx.drawImage(img, 0, 0, width, height);
        const pixels = ctx.getImageData(0, 0, width, height).data;
        const gray = new Uint8Array(width * height);
        for (let i = 0, p = 0; i < pixels.length; i += 4, p++) {
          gray[p] = (pixels[i] * 0.299 + pixels[i + 1] * 0.587 + pixels[i + 2] * 0.114) | 0;
        }
        resolve(classifyInk(gray, width, height));
      } catch {
        resolve(EMPTY);
      }
    };
    img.onerror = () => resolve(EMPTY);
    img.src = src;
  });
}
