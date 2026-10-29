/* Little Elf browser-side resampler and 8 kHz mono PCMU encoder.
 * 160 bytes = 20 ms of RTP payload. Frames are emitted directly from the
 * AudioWorklet to preserve the working VPS microphone timing.
 * Adapted from the tested Home Assistant PTT prototype.
 */
function encodePCMU(sample) {
  let pcm = Math.max(-32768, Math.min(32767, Math.round(sample * 32767)));
  const mask = pcm < 0 ? 0x7f : 0xff;
  if (pcm < 0) pcm = -pcm;
  pcm = Math.min(32635, pcm + 132);
  let segment = 0, tmp = pcm >> 7;
  while (tmp > 1 && segment < 7) { segment++; tmp >>= 1; }
  return (((segment << 4) | ((pcm >> (segment + 3)) & 15)) ^ mask) & 255;
}

class LittleElfPCMULaw extends AudioWorkletProcessor {
  constructor() {
    super();
    this.acc = 0;
    this.sum = 0;
    this.count = 0;
    this.frame = new Uint8Array(160);
    this.index = 0;
  }
  process(inputs, outputs) {
    const samples = inputs[0]?.[0];
    if (samples) {
      for (let i = 0; i < samples.length; ++i) {
        this.sum += samples[i]; this.count++;
        this.acc += 8000;
        if (this.acc >= sampleRate) {
          this.acc -= sampleRate;
          this.frame[this.index++] = encodePCMU(this.sum / this.count);
          this.sum = 0; this.count = 0;
          if (this.index === 160) {
            const result = this.frame;
            this.port.postMessage(result, [result.buffer]);
            this.frame = new Uint8Array(160);
            this.index = 0;
          }
        }
      }
    }
    for (const output of outputs) for (const channel of output) channel.fill(0);
    return true;
  }
}
registerProcessor('little-elf-pcmu', LittleElfPCMULaw);
