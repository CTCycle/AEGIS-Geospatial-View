export interface PreparedImageAttachment {
  name: string;
  dataUrl: string;
  base64: string;
  mimeType: 'image/jpeg';
  width: number;
  height: number;
}

const loadImage = (url: string): Promise<HTMLImageElement> => new Promise((resolve, reject) => {
  const image = new Image();
  image.onload = () => resolve(image);
  image.onerror = () => reject(new Error('The file is not a readable image.'));
  image.src = url;
});

/**
 * Downscale a user-selected image to a bounded JPEG, mirroring the map
 * capture limits so uploads stay small and within the server size bound.
 */
export const prepareImageAttachment = async (
  file: File,
  maxDimension = 1024,
): Promise<PreparedImageAttachment> => {
  if (!file.type.startsWith('image/')) {
    throw new Error('Choose an image file.');
  }
  const objectUrl = URL.createObjectURL(file);
  try {
    const image = await loadImage(objectUrl);
    const scale = Math.min(1, maxDimension / Math.max(image.naturalWidth, image.naturalHeight));
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
    canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
    const context = canvas.getContext('2d');
    if (!context) {
      throw new Error('The image could not be prepared.');
    }
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    const dataUrl = canvas.toDataURL('image/jpeg', 0.8);
    return {
      name: file.name,
      dataUrl,
      base64: dataUrl.slice(dataUrl.indexOf(',') + 1),
      mimeType: 'image/jpeg',
      width: canvas.width,
      height: canvas.height,
    };
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
};
