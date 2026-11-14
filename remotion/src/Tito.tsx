// El Abuelo Tito con el estilo nuevo: MISMA silueta y medidas que tito.py (se tiene que reconocer):
// pelado con nubes de pelo blanco a los costados, antiparras de soldador en la frente, bigote blanco de
// manubrio, guardapolvo blanco con chaleco marrón, moño rojo y el reloj de bolsillo dorado con cadena.
import React from 'react';
import {C, P, Forma, Miembro, Linea, dCirculo, dElipse, dRect, sombra} from './estilo';

const PIEL = '#f6c9a0';
const CANAS = '#eef1f6';
const GUARDAPOLVO = '#fbfbf6';
const CHALECO = '#7a4b2a';
const PANTALON = '#4a4a58';
const ORO = '#e8b53a';
const ORO_OSC = '#b07d1c';
const R = 122;
const CABEZA_Y = -705;
const HOMBRO_Y = -548;

export const Reloj: React.FC<{aguja: number; r: number}> = ({aguja, r}) => {
  const man = (ang: number, largo: number, w: number) => {
    const a = (ang * Math.PI) / 180;
    return <path d={`M0 0 L${Math.sin(a) * largo} ${-Math.cos(a) * largo}`} stroke={C} strokeWidth={w} strokeLinecap="round" />;
  };
  return (
    <g>
      <Forma d={dRect(-12, -r - 30, 24, 22, 6)} fill={ORO_OSC} b={5} sd={4} />
      <Forma d={dCirculo(0, -r - 36, 12)} fill={ORO} b={5} sd={4} />
      <Forma d={dCirculo(0, 0, r)} fill={ORO} sd={r * 0.18} brillo={[-r * 0.45, -r * 0.5, r * 0.22, r * 0.12]} />
      <Forma d={dCirculo(0, 0, r * 0.8)} fill="#fff6dc" b={5} sd={r * 0.08} />
      {Array.from({length: 12}, (_, i) => {
        const a = (i * 30 * Math.PI) / 180;
        return (
          <path key={i} d={`M${Math.sin(a) * r * 0.62} ${-Math.cos(a) * r * 0.62} L${Math.sin(a) * r * 0.74} ${-Math.cos(a) * r * 0.74}`} stroke={C} strokeWidth={i % 3 ? 4 : 7} strokeLinecap="round" />
        );
      })}
      {man(aguja * 12, r * 0.45, 8)}
      {man(aguja, r * 0.62, 5)}
      <circle r={7} fill={C} />
      <path d={`M${-r * 0.55} ${-r * 0.45} Q${-r * 0.62} ${-r * 0.05} ${-r * 0.5} ${r * 0.2}`} fill="none" stroke="#fff" strokeWidth={6} strokeLinecap="round" opacity={0.8} />
    </g>
  );
};

const Cadena: React.FC<{x0: number; y0: number; x1: number; y1: number; caida?: number}> = ({x0, y0, x1, y1, caida = 70}) => {
  const d = `M${x0} ${y0} Q${(x0 + x1) / 2} ${Math.max(y0, y1) + caida} ${x1} ${y1}`;
  return (
    <g>
      <path d={d} fill="none" stroke={C} strokeWidth={13} strokeLinecap="round" />
      <path d={d} fill="none" stroke={ORO} strokeWidth={7} strokeDasharray="9 5" strokeLinecap="round" />
      <path d={d} fill="none" stroke="#fff3c4" strokeWidth={2.5} strokeDasharray="4 10" strokeLinecap="round" transform="translate(-1 -2)" />
    </g>
  );
};

// Un mechón de canas: varios círculos con UN solo contorno, sombra abajo y un brillo.
const Nube: React.FC<{c: [number, number, number][]}> = ({c}) => (
  <g>
    {c.map(([x, y, r], i) => <circle key={'b' + i} cx={x + 1.5} cy={y + 2.5} r={r + 6} fill={C} />)}
    {c.map(([x, y, r], i) => <circle key={'s' + i} cx={x} cy={y} r={r} fill={sombra(CANAS)} />)}
    {c.map(([x, y, r], i) => <circle key={'f' + i} cx={x - r * 0.18} cy={y - r * 0.2} r={r * 0.8} fill={CANAS} />)}
    {c.map(([x, y, r], i) => <path key={'l' + i} d={`M${x - r * 0.4} ${y + r * 0.1} q${r * 0.3} -${r * 0.4} ${r * 0.6} -${r * 0.1}`} fill="none" stroke="#b9bfcc" strokeWidth={3.5} strokeLinecap="round" />)}
  </g>
);

const Ojo: React.FC<{cx: number; cy: number; pa: number}> = ({cx, cy, pa}) => {
  if (pa > 0.85) return <path d={`M${cx - 20} ${cy + 4} Q${cx} ${cy - 12} ${cx + 20} ${cy + 4}`} fill="none" stroke={C} strokeWidth={8} strokeLinecap="round" />;
  const ry = 27 * (1 - Math.max(0, pa));
  return (
    <g>
      <Forma d={dElipse(cx, cy, 22, ry)} fill="#fff" b={5} sd={6}>
        <circle cx={cx + 7 * 0.25} cy={cy + 4} r={Math.min(13, ry * 0.55)} fill="#5a8fc4" />
        <circle cx={cx + 7 * 0.25} cy={cy + 4} r={Math.min(7, ry * 0.3)} fill={C} />
        <circle cx={cx + 6} cy={cy - 1} r={Math.min(4.5, ry * 0.2)} fill="#fff" />
      </Forma>
      <path d={`M${cx - 23} ${cy - ry * 0.2} Q${cx} ${cy - ry - 4} ${cx + 23} ${cy - ry * 0.2}`} fill="none" stroke={C} strokeWidth={6} strokeLinecap="round" />
    </g>
  );
};

const Cabeza: React.FC<{ap: number; pa: number}> = ({ap, pa}) => (
  <g>
    {[-1, 1].map((s) => (
      <Nube key={s} c={[[s * 118, -30, 46], [s * 150, 12, 44], [s * 128, 54, 38], [s * 96, -64, 30]]} />
    ))}
    {([[-34, -24], [4, 6], [40, 30]] as [number, number][]).map(([x, ang]) => (
      <g key={x} transform={`translate(${x} ${-R + 12}) rotate(${ang})`}>
        <Forma d="M-9 0 Q-22 -46 0 -78 Q4 -40 12 0 Z" fill={CANAS} b={5} sd={5} />
      </g>
    ))}
    <Forma d={dCirculo(-R + 6, 14, 26)} fill={PIEL} b={6} sd={8} />
    <Forma d={dCirculo(R - 6, 14, 26)} fill={PIEL} b={6} sd={8} />
    <Forma d={dCirculo(0, 0, R)} fill={PIEL} sd={20} brillo={[-40, -84, 40, 18]}>
      {/* arrugas de la frente y de los ojos */}
      <Linea d="M-50 -100 q50 -12 100 0 M-40 -112 q40 -8 80 0" w={4} o={0.22} />
      <Linea d="M-84 10 l-12 -6 M-84 20 l-14 2 M84 10 l12 -6 M84 20 l14 2" w={4} o={0.3} />
    </Forma>
    {[-1, 1].map((s) => <ellipse key={s} cx={s * 74} cy={34} rx={24} ry={14} fill={P.rosa} opacity={0.45} />)}
    {/* antiparras de soldador: correa de cuero, lentes de bronce con vidrio verde */}
    <Forma d={`M${-R + 4} -66 Q0 -92 ${R - 4} -66 L${R - 2} -44 Q0 -70 ${-R + 2} -44 Z`} fill="#6b4a2e" b={5} sd={6}>
      <Linea d={`M${-R + 10} -56 Q0 -80 ${R - 10} -56`} w={3} o={0.5} color="#a87b50" />
    </Forma>
    {[-1, 1].map((s) => (
      <g key={s}>
        <Forma d={dCirculo(s * 44, -64, 33)} fill="#c98a3a" b={6} sd={8} brillo={[s * 44 - 14, -80, 8, 5]} />
        <Forma d={dCirculo(s * 44, -64, 22)} fill="#5fd1a8" b={5} sd={6}>
          <path d={`M${s * 44 - 14} -60 l20 -16`} stroke="#fff" strokeWidth={5} strokeLinecap="round" opacity={0.7} />
        </Forma>
        {[0, 90, 180, 270].map((a) => (
          <circle key={a} cx={s * 44 + Math.cos((a * Math.PI) / 180) * 28} cy={-64 + Math.sin((a * Math.PI) / 180) * 28} r={2.6} fill="#7a4b20" />
        ))}
      </g>
    ))}
    <Forma d={dRect(-12, -70, 24, 12, 4)} fill="#6b4a2e" b={4} sd={3} />
    {[-1, 1].map((s) => (
      <g key={s} transform={`translate(${s * 44} -28)`}>
        <Forma d="M-26 6 Q0 -16 26 6 Q0 -2 -26 6 Z" fill={CANAS} b={5} sd={4} />
      </g>
    ))}
    <Ojo cx={-44} cy={4} pa={pa} />
    <Ojo cx={44} cy={4} pa={pa} />
    {ap < 0.08 ? (
      <path d="M-26 74 Q0 94 26 74" fill="none" stroke={C} strokeWidth={8} strokeLinecap="round" />
    ) : (
      <Forma d={dElipse(0, 78 + 8 * ap, 26, 6 + 20 * ap)} fill="#5a1e2a" b={5} sinSombra>
        <rect x={-26} y={72 + 8 * ap - 20 * ap} width={52} height={9} fill="#fffaf0" />
        {ap > 0.4 ? <ellipse cx={0} cy={86 + 12 * ap} rx={14} ry={6 * ap + 2} fill="#ff7a8a" /> : null}
      </Forma>
    )}
    <Forma d={dElipse(0, 30, 23, 19)} fill="#f0a585" b={6} sd={8} brillo={[-8, 22, 7, 5]} />
    <Forma d="M0 48 Q-26 38 -58 50 Q-86 58 -96 40 Q-100 70 -66 76 Q-30 80 0 62 Q30 80 66 76 Q100 70 96 40 Q86 58 58 50 Q26 38 0 48 Z" fill={CANAS} b={6} sd={8}>
      <Linea d="M-20 56 q-20 4 -44 10 M20 56 q20 4 44 10 M-30 62 q-16 6 -40 8 M30 62 q16 6 40 8" w={3} o={0.3} />
    </Forma>
  </g>
);

const Brazo: React.FC<{x0: number; y0: number; pts: [number, number][]}> = ({x0, y0, pts}) => {
  const todos: [number, number][] = [[x0, y0], ...pts];
  const [x, y] = todos[todos.length - 1];
  const [xp, yp] = todos[todos.length - 2];
  return (
    <g>
      <Miembro pts={todos} color={GUARDAPOLVO} ancho={44} />
      <Miembro pts={[[xp + (x - xp) * 0.8, yp + (y - yp) * 0.8], [xp + (x - xp) * 0.92, yp + (y - yp) * 0.92]]} color="#dfe3ea" ancho={48} b={5} />
      <Forma d={dCirculo(x, y, 25)} fill={PIEL} b={6} sd={8} brillo={[x - 8, y - 9, 7, 5]} />
    </g>
  );
};

export const Tito: React.FC<{pose: string; ap: number; pa: number; ag: number; re: number; inc: number}> = ({pose, ap, pa, ag, re, inc}) => {
  const top = HOMBRO_Y * (1 + 0.012 * re);
  const hx = 108;
  const hy = top + 14;
  const bolsillo: [number, number] = [-36, -330];
  let adelante: React.ReactNode;
  if (pose === 'reloj') {
    adelante = (
      <g>
        <Brazo x0={-hx} y0={hy} pts={[[-190, -430], [-128, -350]]} />
        <Brazo x0={hx} y0={hy} pts={[[205, -620], [238, -760]]} />
        <Cadena x0={bolsillo[0]} y0={bolsillo[1]} x1={238} y1={-792} caida={160} />
        <g transform="translate(248 -842) rotate(8)"><Reloj aguja={ag} r={70} /></g>
        <Forma d={dCirculo(238, -760, 25)} fill={PIEL} b={6} sd={8} />
      </g>
    );
  } else {
    adelante = (
      <g>
        <Brazo x0={-hx} y0={hy} pts={[[-176, -420], [-168, -300]]} />
        <Cadena x0={bolsillo[0]} y0={bolsillo[1]} x1={-168} y1={-300} caida={40} />
        <Cadena x0={-168} y0={-300} x1={-168} y1={-206} caida={0} />
        <g transform="translate(-168 -150) rotate(-6)"><Reloj aguja={ag} r={52} /></g>
        {pose === 'senala' ? (
          <g>
            <Brazo x0={hx} y0={hy} pts={[[220, -560], [330, -606]]} />
            <path d="M342 -612 L392 -634" stroke={C} strokeWidth={26} strokeLinecap="round" />
            <path d="M342 -612 L392 -634" stroke={PIEL} strokeWidth={12} strokeLinecap="round" />
          </g>
        ) : (
          <Brazo x0={hx} y0={hy} pts={[[196, -640], [214, -768]]} />
        )}
      </g>
    );
  }
  return (
    <g>
      {[-1, 1].map((s) => {
        const x = s * 40;
        return (
          <g key={s}>
            <Miembro pts={[[x, -200], [x, -30]]} color={PANTALON} ancho={46} />
            <Forma d={`M${x - s * 30} 0 Q${x - s * 30} -46 ${x + s * 8} -46 Q${x + s * 58} -46 ${x + s * 60} 0 Z`} fill="#5b3a22" b={7} sd={8} brillo={[x + s * 16, -34, 12, 6]}>
              <rect x={Math.min(x - s * 30, x + s * 60)} y={-10} width={90} height={10} fill="#3a2414" />
            </Forma>
          </g>
        );
      })}
      {/* guardapolvo largo (corte A) */}
      <Forma d={`M-112 ${top} Q-150 -380 -168 -176 Q-84 -160 0 -170 Q84 -160 168 -176 Q150 -380 112 ${top} Q0 ${top - 26} -112 ${top} Z`} fill={GUARDAPOLVO} sd={26} brillo={[-110, -420, 20, 90]}>
        <Linea d="M-130 -300 Q-120 -240 -140 -190 M130 -300 Q120 -240 140 -190 M-80 -220 q4 30 -4 50 M80 -220 q-4 30 4 50" w={4} o={0.22} />
      </Forma>
      <Forma d={`M-56 ${top - 6} L-46 -300 L0 -270 L46 -300 L56 ${top - 6} Z`} fill={CHALECO} b={6} sd={12} />
      <Forma d={`M-30 ${top - 10} L0 -470 L30 ${top - 10} Z`} fill="#bfe3ff" b={5} sd={6} />
      {[-420, -370, -320].map((y) => <Forma key={y} d={dCirculo(0, y, 7)} fill={ORO_OSC} b={3} sinSombra />)}
      {[-1, 1].map((s) => (
        <Forma key={s} d={`M${s * 58} ${top - 4} L${s * 30} -430 L${s * 70} -460 L${s * 96} ${top + 6} Z`} fill={GUARDAPOLVO} b={6} sd={8} />
      ))}
      <path d="M-50 -296 L-56 -176 M50 -296 L56 -176" stroke={C} strokeWidth={5} opacity={0.6} />
      {/* bolsillo con lapiceras */}
      {[P.rojo, P.azul].map((c, k) => <Forma key={c} d={dRect(84 + k * 22, -356, 12, 40, 4)} fill={c} b={3} sd={3} />)}
      <Forma d={dRect(74, -330, 60, 56, 6)} fill={GUARDAPOLVO} b={5} sd={7} />
      {/* moño rojo */}
      <Forma d={`M0 ${top - 4} L-34 ${top - 22} L-34 ${top + 18} Z`} fill={P.rojo} b={5} sd={6} />
      <Forma d={`M0 ${top - 4} L34 ${top - 22} L34 ${top + 18} Z`} fill={P.rojo} b={5} sd={6} />
      <Forma d={dCirculo(0, top - 4, 10)} fill={P.rojo} b={5} sd={3} />
      <g transform={`translate(0 ${CABEZA_Y}) rotate(${inc})`}>
        <Cabeza ap={ap} pa={pa} />
      </g>
      {adelante}
    </g>
  );
};
