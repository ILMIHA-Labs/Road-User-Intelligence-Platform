"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Speech-to-text (push-to-talk) over the Web Speech API.
 * Feature-detected: `supported` is false where SpeechRecognition is absent
 * (e.g. Firefox) so the UI can fall back to text input. Recognition is
 * cloud-based in current browsers — callers should disclose that and keep it
 * opt-in (see wayfinder #16 / research #20).
 */
export function useSpeechRecognition(onFinal: (text: string) => void) {
  const [supported, setSupported] = useState(false);
  const [listening, setListening] = useState(false);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const onFinalRef = useRef(onFinal);
  onFinalRef.current = onFinal;

  useEffect(() => {
    if (typeof window === "undefined") return;
    const Ctor = window.SpeechRecognition ?? window.webkitSpeechRecognition;
    if (!Ctor) return;
    setSupported(true);
    const rec = new Ctor();
    rec.lang = "en-US";
    rec.continuous = false;
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    rec.onresult = (event) => {
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        if (result.isFinal) {
          const text = result[0]?.transcript?.trim();
          if (text) onFinalRef.current(text);
        }
      }
    };
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    recognitionRef.current = rec;
    return () => rec.abort();
  }, []);

  const start = useCallback(() => {
    const rec = recognitionRef.current;
    if (!rec || listening) return;
    try {
      rec.start();
      setListening(true);
    } catch {
      setListening(false);
    }
  }, [listening]);

  const stop = useCallback(() => {
    recognitionRef.current?.stop();
    setListening(false);
  }, []);

  return { supported, listening, start, stop };
}

/**
 * Text-to-speech over the Web Speech API. Universally supported, offline,
 * nothing leaves the device.
 */
export function useSpeechSynthesis() {
  const [supported, setSupported] = useState(false);
  const [speaking, setSpeaking] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      setSupported(true);
    }
  }, []);

  const speak = useCallback((text: string) => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    const clean = text.trim();
    if (!clean) return;
    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(clean);
    utter.onstart = () => setSpeaking(true);
    utter.onend = () => setSpeaking(false);
    utter.onerror = () => setSpeaking(false);
    window.speechSynthesis.speak(utter);
  }, []);

  const cancel = useCallback(() => {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
      setSpeaking(false);
    }
  }, []);

  return { supported, speaking, speak, cancel };
}
