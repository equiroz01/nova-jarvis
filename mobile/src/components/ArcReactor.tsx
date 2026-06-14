/**
 * ArcReactor.tsx — React Native port of the web arc-reactor visualizer
 * (backend/app/static/js/waveform.js + the ring/core-glow CSS animations).
 *
 * Faithful-enough recreation: concentric rings, 12 gear segments, 24 radial
 * bars, a sweep line and a breathing core. Each animated layer is its own
 * absolutely-positioned <Svg> inside an Animated.View that rotates with the
 * native driver, so spins stay smooth off the JS thread. Rotation speed, the
 * core-breath rate and the accent color all change with `mode`, matching the
 * web states (idle=cyan, listening=green, thinking=amber, speaking=bright cyan).
 */
import React, { useEffect, useMemo, useRef } from 'react';
import { Animated, Easing, StyleSheet, Text, View, ViewStyle } from 'react-native';
import Svg, { Circle, G, Line, Rect, Defs, RadialGradient, Stop } from 'react-native-svg';

export type ReactorMode = 'idle' | 'listening' | 'thinking' | 'speaking';

const C = 120; // center of the 240x240 viewBox

const COLOR: Record<ReactorMode, string> = {
  idle: '#00aaff',
  listening: '#00ee66',
  thinking: '#ffaa00',
  speaking: '#33ccff',
};

// Per-mode durations (ms) for [outer, gears, bars, sweep] and the core breath.
const SPEED: Record<ReactorMode, { outer: number; gears: number; bars: number; sweep: number; breath: number }> = {
  idle:      { outer: 20000, gears: 15000, bars: 8000, sweep: 3000, breath: 3000 },
  listening: { outer: 14000, gears: 4000,  bars: 3000, sweep: 1500, breath: 1000 },
  thinking:  { outer: 9000,  gears: 2000,  bars: 1500, sweep: 1000, breath: 500 },
  speaking:  { outer: 3000,  gears: 2000,  bars: 1500, sweep: 800,  breath: 600 },
};

/** Rotates its children continuously over `duration` ms (native driver). */
function Spin({
  duration,
  reverse,
  size,
  children,
}: {
  duration: number;
  reverse?: boolean;
  size: number;
  children: React.ReactNode;
}) {
  const v = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    v.setValue(0);
    const anim = Animated.loop(
      Animated.timing(v, { toValue: 1, duration, easing: Easing.linear, useNativeDriver: true }),
    );
    anim.start();
    return () => anim.stop();
  }, [duration, v]);
  const rotate = v.interpolate({
    inputRange: [0, 1],
    outputRange: reverse ? ['360deg', '0deg'] : ['0deg', '360deg'],
  });
  return (
    <Animated.View style={[StyleSheet.absoluteFill, { width: size, height: size, transform: [{ rotate }] }]}>
      {children}
    </Animated.View>
  );
}

export default function ArcReactor({
  mode = 'idle',
  size = 200,
  style,
}: {
  mode?: ReactorMode;
  size?: number;
  style?: ViewStyle;
}) {
  const color = COLOR[mode];
  const speed = SPEED[mode];

  // Core breath (scale + opacity), restarted when the rate changes.
  const breath = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    breath.setValue(0);
    const anim = Animated.loop(
      Animated.sequence([
        Animated.timing(breath, { toValue: 1, duration: speed.breath, easing: Easing.inOut(Easing.ease), useNativeDriver: true }),
        Animated.timing(breath, { toValue: 0, duration: speed.breath, easing: Easing.inOut(Easing.ease), useNativeDriver: true }),
      ]),
    );
    anim.start();
    return () => anim.stop();
  }, [speed.breath, breath]);
  const coreScale = breath.interpolate({ inputRange: [0, 1], outputRange: [0.92, 1.12] });
  const coreOpacity = breath.interpolate({ inputRange: [0, 1], outputRange: [0.6, 1] });

  // 24 radial bars (lengths/weights mirror the web).
  const bars = useMemo(() => {
    const out: { x1: number; y1: number; x2: number; y2: number; w: number; o: number }[] = [];
    for (let i = 0; i < 24; i++) {
      const angle = i * 15;
      const len = i % 3 === 0 ? 20 : i % 2 === 0 ? 14 : 9;
      const r1 = 75;
      const r2 = r1 + len;
      const rad = (angle * Math.PI) / 180;
      out.push({
        x1: C + r1 * Math.sin(rad),
        y1: C - r1 * Math.cos(rad),
        x2: C + r2 * Math.sin(rad),
        y2: C - r2 * Math.cos(rad),
        w: i % 3 === 0 ? 3 : 2,
        o: i % 3 === 0 ? 0.8 : 0.4,
      });
    }
    return out;
  }, []);

  const gears = useMemo(() => Array.from({ length: 12 }, (_, i) => i * 30), []);

  return (
    <View style={[{ width: size, height: size, alignItems: 'center', justifyContent: 'center' }, style]}>
      {/* Static rings (solid circles rotate imperceptibly, so they stay still). */}
      <Svg style={StyleSheet.absoluteFill} width={size} height={size} viewBox="0 0 240 240">
        <Circle cx={C} cy={C} r={95} fill="none" stroke={color} strokeWidth={2} opacity={0.6} />
        <Circle cx={C} cy={C} r={70} fill="none" stroke={color} strokeWidth={1.5} opacity={0.6} />
        <Circle cx={C} cy={C} r={52} fill="none" stroke={color} strokeWidth={2} opacity={0.9} />
      </Svg>

      {/* Outer dashed ring */}
      <Spin duration={speed.outer} size={size}>
        <Svg width={size} height={size} viewBox="0 0 240 240">
          <Circle cx={C} cy={C} r={112} fill="none" stroke={color} strokeWidth={2.5} strokeDasharray="8 4" opacity={0.7} />
        </Svg>
      </Spin>

      {/* Gear segments */}
      <Spin duration={speed.gears} size={size}>
        <Svg width={size} height={size} viewBox="0 0 240 240">
          <G>
            {gears.map((a, i) => (
              <Rect
                key={i}
                x={C - 7}
                y={3}
                width={14}
                height={10}
                rx={1}
                fill={color}
                fillOpacity={0.15}
                stroke={color}
                strokeWidth={0.8}
                origin={`${C}, ${C}`}
                rotation={a}
              />
            ))}
          </G>
        </Svg>
      </Spin>

      {/* Radial bars */}
      <Spin duration={speed.bars} size={size}>
        <Svg width={size} height={size} viewBox="0 0 240 240">
          {bars.map((b, i) => (
            <Line
              key={i}
              x1={b.x1}
              y1={b.y1}
              x2={b.x2}
              y2={b.y2}
              stroke={color}
              strokeWidth={b.w}
              strokeLinecap="round"
              opacity={b.o}
            />
          ))}
        </Svg>
      </Spin>

      {/* Sweep line */}
      <Spin duration={speed.sweep} size={size}>
        <Svg width={size} height={size} viewBox="0 0 240 240">
          <Line x1={C} y1={C} x2={C + 105} y2={C} stroke={color} strokeWidth={1.5} opacity={0.6} />
        </Svg>
      </Spin>

      {/* Breathing core glow */}
      <Animated.View
        style={[StyleSheet.absoluteFill, { alignItems: 'center', justifyContent: 'center', opacity: coreOpacity, transform: [{ scale: coreScale }] }]}
        pointerEvents="none"
      >
        <Svg width={size} height={size} viewBox="0 0 240 240">
          <Defs>
            <RadialGradient id="coreGrad" cx="50%" cy="50%" r="50%">
              <Stop offset="0" stopColor={color} stopOpacity={0.95} />
              <Stop offset="0.5" stopColor={color} stopOpacity={0.45} />
              <Stop offset="1" stopColor={color} stopOpacity={0} />
            </RadialGradient>
          </Defs>
          <Circle cx={C} cy={C} r={48} fill="url(#coreGrad)" />
        </Svg>
      </Animated.View>

      {/* Center label */}
      <Text
        style={{
          color,
          fontSize: size * 0.1,
          fontWeight: '700',
          letterSpacing: 2,
          textShadowColor: color,
          textShadowRadius: 12,
        }}
      >
        NOVA
      </Text>
    </View>
  );
}
