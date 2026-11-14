// Los personajes del elenco con el estilo nuevo. MISMO esqueleto que personajes.py (cabeza R 118, brazos
// 112 + 104, hombros a ±92, piernas a ±42, origen en el piso entre los pies): el chequeo de composición del
// motor actual (brazos que cruzan caras, personajes que se pisan) sigue valiendo tal cual.
import React from 'react';
import {C, P, Forma, Miembro, Linea, dCirculo, dElipse, dRect, mezclar, sombra, luz} from './estilo';
import type {Estado, Personaje} from './tipos';

const R = 118;
const L1 = 112;
const L2 = 104;
const rad = (g: number) => (g * Math.PI) / 180;
const ZAPATO = '#4a3a44';

const pestanas = (p: Personaje) => ['mama', 'vecina'].includes(p.nombre) || p.peinado === 'largo';
const iris = (p: Personaje) => (p.piel === '#b97a52' || p.piel === '#7d4f33' ? '#3b2416' : p.pelo === '#e2b04a' ? '#3a7fc4' : '#6b4226');

// ---- cabeza de frente ----------------------------------------------------------------------------
const Ojo: React.FC<{cx: number; cy: number; e: Estado; p: Personaje; s: number}> = ({cx, cy, e, p, s}) => {
  const cierre = Math.max(0, Math.min(1, e.parpadeo));
  if (cierre > 0.85) {
    return <path d={`M${cx - 20} ${cy} Q${cx} ${cy + 11} ${cx + 20} ${cy}`} fill="none" stroke={C} strokeWidth={7} strokeLinecap="round" />;
  }
  const ry = 26 * (1 - cierre);
  const ir = Math.min(13, ry * 0.62);
  const ix = cx + 6 * e.mirada;
  return (
    <g>
      <Forma d={dElipse(cx, cy, 20, ry)} fill="#ffffff" b={5} sd={6}>
        <circle cx={ix} cy={cy + 3} r={ir} fill={iris(p)} />
        <circle cx={ix} cy={cy + 3} r={ir * 0.55} fill={C} />
        <circle cx={ix + 4} cy={cy - 2} r={ir * 0.32} fill="#fff" />
        <circle cx={ix - 3} cy={cy + 7} r={ir * 0.14} fill="#fff" />
      </Forma>
      {/* párpado de arriba: da la expresión */}
      <path d={`M${cx - 21} ${cy - ry * 0.25} Q${cx} ${cy - ry - 3} ${cx + 21} ${cy - ry * 0.25}`} fill="none" stroke={C} strokeWidth={6} strokeLinecap="round" />
      {pestanas(p) ? <path d={`M${cx + s * 19} ${cy - ry * 0.45} l${s * 9} -7 M${cx + s * 14} ${cy - ry * 0.8} l${s * 7} -9`} stroke={C} strokeWidth={4.5} strokeLinecap="round" /> : null}
    </g>
  );
};

const Ceja: React.FC<{s: number; tipo: string; color: string}> = ({s, tipo, color}) => {
  const [dy, rot] = ({normal: [0, 0], arriba: [-16, -6], enojo: [2, 14], triste: [-6, -16]} as Record<string, [number, number]>)[tipo] ?? [0, 0];
  return (
    <g transform={`translate(${s * 42} ${-50 + dy}) scale(${s} 1) rotate(${rot})`}>
      <Forma d="M-24 5 Q-4 -12 24 -2 Q22 4 18 4 Q-2 -2 -22 9 Z" fill={color} b={4} sinSombra />
    </g>
  );
};

const Boca: React.FC<{e: Estado; y?: number}> = ({e, y = 58}) => {
  const ap = Math.max(0, Math.min(1, e.apertura));
  if (e.boca === 'cerrada' || e.boca === 'sonrisa' || ap < 0.08) {
    const [an, cu] = e.boca === 'cerrada' ? [30, 14] : [40, 26];
    return (
      <g>
        <path d={`M${-an} ${y - 4} Q0 ${y + cu} ${an} ${y - 4}`} fill="none" stroke={C} strokeWidth={7} strokeLinecap="round" />
        <path d={`M${-an - 4} ${y - 9} q3 4 6 8 M${an + 4} ${y - 9} q-3 4 -6 8`} fill="none" stroke={C} strokeWidth={4} strokeLinecap="round" opacity={0.6} />
      </g>
    );
  }
  const [rx, ry] = ({a: [32, 8 + 30 * ap], e: [40, 6 + 16 * ap], o: [16 + 6 * ap, 10 + 24 * ap]} as Record<string, [number, number]>)[e.boca] ?? [30, 8 + 26 * ap];
  const cy = y + ry * 0.35;
  return (
    <Forma d={dElipse(0, cy, rx, ry)} fill="#5a1e2a" b={5} sinSombra>
      <rect x={-rx} y={cy - ry - 2} width={rx * 2} height={Math.min(ry * 0.45, 12)} fill="#fffaf0" />
      {ry > 14 ? <ellipse cx={0} cy={cy + ry * 0.6} rx={rx * 0.6} ry={ry * 0.42} fill="#ff7a8a" /> : null}
    </Forma>
  );
};

const PeloArriba: React.FC<{p: Personaje}> = ({p}) => {
  const c = p.pelo;
  if (p.peinado === 'pelado') return null;
  if (p.peinado === 'rulos') {
    const bolas: [number, number][] = [[-80, -70], [-40, -100], [0, -110], [40, -100], [80, -70], [-104, -26], [104, -26]];
    return (
      <g>
        {bolas.map(([x, y], i) => (
          <Forma key={i} d={dCirculo(x, y, 40)} fill={c} b={6} sd={10} brillo={[x - 12, y - 14, 12, 7]}>
            <Linea d={`M${x - 14} ${y + 6} q10 -14 22 -4`} w={4} o={0.3} />
          </Forma>
        ))}
      </g>
    );
  }
  if (p.peinado === 'jopo') {
    const d = `M${-R + 4} -20 Q${-R} ${-R - 10} -10 ${-R - 30} Q60 ${-R - 62} ${R - 10} ${-R + 4} Q${R + 6} -60 ${R - 6} -22 Q60 -70 10 -64 Q-50 -62 ${-R + 4} -20 Z`;
    return (
      <Forma d={d} fill={c} sd={14} brillo={[10, -R - 18, 44, 12]}>
        <Linea d={`M-60 -78 Q-10 -120 50 -${R + 18} M-20 -66 Q30 -100 90 -${R - 6} M-90 -48 Q-60 -96 -10 -${R + 10}`} w={5} o={0.28} />
      </Forma>
    );
  }
  const d = `M${-R + 2} -14 Q${-R + 6} ${-R - 14} 0 ${-R - 12} Q${R - 6} ${-R - 14} ${R - 2} -14 Q50 -64 0 -60 Q-50 -64 ${-R + 2} -14 Z`;
  if (p.peinado === 'largo') {
    // flequillo de costado (pelo largo): la cara se lee distinta a la del nene de pelo corto
    const fl = `M${-R + 2} -6 Q${-R + 6} ${-R - 14} 0 ${-R - 12} Q${R - 6} ${-R - 14} ${R - 2} -6 Q${R - 20} -70 40 -78 Q-10 -60 -60 -30 Q-90 -16 ${-R + 2} -6 Z`;
    return (
      <Forma d={fl} fill={c} sd={12} brillo={[-20, -R + 2, 46, 10]}>
        <Linea d={`M50 -${R + 4} Q20 -90 -50 -40 M80 -${R - 14} Q50 -80 0 -62 M-40 -${R} Q-80 -70 -100 -20`} w={5} o={0.28} />
      </Forma>
    );
  }
  return (
    <Forma d={d} fill={c} sd={12} brillo={[-30, -R + 4, 40, 10]}>
      <Linea d={`M-70 -64 Q-40 -100 -10 -${R - 2} M10 -62 Q40 -96 60 -${R - 10} M-100 -30 Q-90 -70 -60 -96`} w={5} o={0.28} />
    </Forma>
  );
};

const Sombrero: React.FC<{p: Personaje; perfil?: boolean}> = ({p, perfil}) => {
  const c = p.color_sombrero;
  const dx = perfil ? 8 : 0;
  if (p.sombrero === 'gorra') {
    return (
      <g>
        <Forma d={`M${-R + 4 + dx} -40 Q${-R + 10 + dx} ${-R - 30} ${dx} ${-R - 30} Q${R - 10 + dx} ${-R - 30} ${R - 4 + dx} -40 Z`} fill={c} brillo={[dx - 30, -R - 4, 40, 12]}>
          <Linea d={`M${dx} ${-R - 30} L${dx} -42 M${dx - 60} ${-R + 2} Q${dx - 40} -60 ${dx - 50} -42`} w={4} o={0.35} />
        </Forma>
        <Forma d={`M${R - 30 + dx} -44 Q${R + 70 + dx} -46 ${R + 76 + dx} -30 Q${R + 20 + dx} -24 ${R - 30 + dx} -30 Z`} fill={sombra(c)} sd={4} />
        <circle cx={dx} cy={-R - 30} r={9} fill={mezclar(c, '#000', 0.3)} stroke={C} strokeWidth={4} />
      </g>
    );
  }
  if (p.sombrero === 'galera') {
    return (
      <g>
        <Forma d={`M${-80 + dx} ${-R + 10} L${-74 + dx} ${-R - 120} L${74 + dx} ${-R - 120} L${80 + dx} ${-R + 10} Z`} fill={c} sd={18} brillo={[-40 + dx, -R - 70, 10, 40]} />
        <Forma d={dRect(-78 + dx, -R - 20, 156, 24)} fill={P.rojo} b={5} sd={5} />
        <Forma d={dElipse(dx, -R + 12, 130, 22)} fill={c} sd={8} />
      </g>
    );
  }
  return null;
};

const Cabeza: React.FC<{p: Personaje; e: Estado}> = ({p, e}) => {
  const ceja = mezclar(p.pelo, '#000', 0.25);
  return (
    <g>
      {p.peinado === 'largo' ? (
        <Forma d={`M${-R - 14} -10 Q${-R - 24} ${R + 70} ${-R + 30} ${R + 60} L${R - 30} ${R + 60} Q${R + 24} ${R + 70} ${R + 14} -10 Z`} fill={sombra(p.pelo)} sd={10}>
          <Linea d={`M${-R + 4} 20 Q${-R + 10} 90 ${-R + 40} ${R + 50} M${R - 4} 20 Q${R - 10} 90 ${R - 40} ${R + 50}`} w={5} o={0.3} />
        </Forma>
      ) : null}
      {[-1, 1].map((s) => (
        <Forma key={s} d={dCirculo(s * (R - 4), 12, 26)} fill={p.piel} b={6} sd={8}>
          <path d={`M${s * (R - 4) - s * 8} 0 q${s * 12} 10 0 24`} fill="none" stroke={sombra(p.piel)} strokeWidth={6} strokeLinecap="round" />
        </Forma>
      ))}
      <Forma d={dCirculo(0, 0, R)} fill={p.piel} sd={18} brillo={[-44, -58, 34, 20]} />
      <PeloArriba p={p} />
      {p.cachetes
        ? [-1, 1].map((s) => <ellipse key={s} cx={s * 66} cy={40} rx={23} ry={13} fill={P.rosa} opacity={0.42} />)
        : null}
      <Ojo cx={-42} cy={-8} e={e} p={p} s={-1} />
      <Ojo cx={42} cy={-8} e={e} p={p} s={1} />
      <Ceja s={-1} tipo={e.cejas} color={ceja} />
      <Ceja s={1} tipo={e.cejas} color={ceja} />
      {/* nariz chica con volumen */}
      <Forma d={dElipse(0, 22, 15, 12)} fill={mezclar(p.piel, '#e07a5f', 0.22)} b={5} sd={6} brillo={[-5, 17, 5, 3]} />
      {p.anteojos ? (
        <g>
          {[-42, 42].map((x) => (
            <circle key={x} cx={x} cy={-8} r={32} fill="#cdeeff" fillOpacity={0.22} stroke={C} strokeWidth={6.5} />
          ))}
          <path d="M-10 -10 Q0 -18 10 -10" fill="none" stroke={C} strokeWidth={6} />
          <path d="M-60 -26 l10 -6 M24 -26 l10 -6" stroke="#fff" strokeWidth={4} strokeLinecap="round" opacity={0.7} />
        </g>
      ) : null}
      {p.bigote ? <Forma d="M-44 44 Q-22 26 0 40 Q22 26 44 44 Q22 58 0 48 Q-22 58 -44 44 Z" fill={p.pelo} b={5} sd={6} /> : null}
      <Boca e={e} />
      <Sombrero p={p} />
    </g>
  );
};

// ---- de frente ----------------------------------------------------------------------------------
const Frente: React.FC<{p: Personaje; e: Estado}> = ({p, e}) => {
  const k = p.alto_cuerpo;
  const resp = 1 + 0.014 * e.respiracion;
  const pisoT = -150 * k;
  const tope = pisoT - 270 * k * resp;
  const cyC = tope - R + 22;
  const hy = tope + 38;
  const piernas = [-1, 1].map((s) => {
    const x = s * 42;
    const lev = Math.max(0, Math.min(1, s < 0 ? e.pierna_izq : e.pierna_der));
    const ag = Math.max(0, Math.min(1, e.agachar));
    const cad: [number, number] = [x, pisoT + 10];
    const pieY = -28 - 70 * lev;
    const rod: [number, number] = [x + s * (26 * lev + 30 * ag), (cad[1] + pieY) / 2 - 6 * lev];
    const pie: [number, number] = [x + s * 6 * lev, pieY];
    const dy = pieY + 28;
    return (
      <g key={s}>
        <Miembro pts={[cad, rod, pie]} color={p.pantalon} ancho={46} />
        <Forma d={`M${x - s * 30} ${dy} Q${x - s * 30} ${dy - 46} ${x + s * 6} ${dy - 46} Q${x + s * 50} ${dy - 46} ${x + s * 52} ${dy} Z`} fill={ZAPATO} b={7} sd={8} brillo={[x + s * 14, dy - 34, 12, 6]}>
          <rect x={Math.min(x - s * 30, x + s * 52)} y={dy - 10} width={82} height={10} fill="#e9e4dc" />
          <path d={`M${x - s * 6} ${dy - 40} l${s * 16} 8 M${x - s * 2} ${dy - 30} l${s * 16} 8`} stroke="#e9e4dc" strokeWidth={4} strokeLinecap="round" />
        </Forma>
      </g>
    );
  });
  const torso = `M-118 ${pisoT} L118 ${pisoT} Q124 ${tope + 40} 98 ${tope + 10} Q88 ${tope} 0 ${tope} Q-88 ${tope} -98 ${tope + 10} Q-124 ${tope + 40} -118 ${pisoT} Z`;
  const brazo = (lado: number, [hombro, codo]: [number, number]) => {
    const x0 = lado * 92;
    const a1 = rad(hombro);
    const a2 = rad(hombro + codo);
    const x1 = x0 + lado * Math.sin(a1) * L1;
    const y1 = hy + Math.cos(a1) * L1;
    const x2 = x1 + lado * Math.sin(a2) * L2;
    const y2 = y1 + Math.cos(a2) * L2;
    const xm = x1 + (x2 - x1) * 0.8;
    const ym = y1 + (y2 - y1) * 0.8;
    return (
      <g key={lado}>
        <Miembro pts={[[x0, hy], [x1, y1], [x2, y2]]} color={p.ropa} ancho={36} />
        <Miembro pts={[[xm, ym], [x1 + (x2 - x1) * 0.9, y1 + (y2 - y1) * 0.9]]} color={luz(p.ropa)} ancho={40} b={5} />
        <Forma d={dCirculo(x2, y2, 24)} fill={p.piel} b={6} sd={8} brillo={[x2 - 8, y2 - 9, 7, 5]} />
        <Forma d={dCirculo(x2 + lado * 16, y2 - 12, 10)} fill={p.piel} b={5} sd={4} />
      </g>
    );
  };
  return (
    <g>
      {piernas}
      <Forma d={torso} fill={p.ropa} sd={22} brillo={[-58, tope + 60, 26, 60]}>
        {/* cinturón, costura del medio con botones, bolsillo y dos pliegues */}
        <rect x={-130} y={pisoT - 34} width={260} height={30} fill={mezclar(p.pantalon, '#000', 0.25)} />
        <rect x={-16} y={pisoT - 36} width={32} height={34} rx={5} fill="none" stroke={P.oro} strokeWidth={6} />
        <Linea d={`M0 ${tope + 30} L0 ${pisoT - 36}`} w={5} o={0.3} />
        {[0.25, 0.5, 0.75].map((f) => (
          <circle key={f} cx={0} cy={tope + 30 + (pisoT - 66 - tope) * f} r={6.5} fill={luz(p.ropa)} stroke={C} strokeWidth={3} />
        ))}
        <path d={`M38 ${tope + 70} h48 v44 q-24 8 -48 0 Z`} fill="none" stroke={C} strokeWidth={4} opacity={0.45} />
        <Linea d={`M-104 ${pisoT - 60} Q-80 ${pisoT - 100} -86 ${pisoT - 150} M100 ${pisoT - 56} Q84 ${pisoT - 96} 90 ${pisoT - 140}`} w={4} o={0.25} />
      </Forma>
      {/* cuello de la camisa */}
      <Forma d={`M-34 ${tope - 2} L0 ${tope + 34} L-6 ${tope + 44} L-46 ${tope + 14} Z`} fill={P.crema} b={5} sd={5} />
      <Forma d={`M34 ${tope - 2} L0 ${tope + 34} L6 ${tope + 44} L46 ${tope + 14} Z`} fill={P.crema} b={5} sd={5} />
      {brazo(-1, e.brazo_izq)}
      {brazo(1, e.brazo_der)}
      <g transform={`translate(0 ${cyC}) rotate(${e.inclinacion})`}>
        <Cabeza p={p} e={e} />
      </g>
    </g>
  );
};

// ---- de perfil (mirando a la derecha; a la izquierda se espeja) ---------------------------------
const Perfil: React.FC<{p: Personaje; e: Estado}> = ({p, e}) => {
  const k = p.alto_cuerpo;
  const resp = 1 + 0.014 * e.respiracion;
  const pisoT = -150 * k;
  const tope = pisoT - 270 * k * resp;
  const hy = tope + 38;
  const cy = tope - R + 22;
  const largo = -28 - (pisoT + 10);
  const zan = (e.corre ? 40 : 28) * e.zancada;
  const piernas = [-1, 1].map((signo) => {
    const a = rad(signo * zan);
    const cad: [number, number] = [0, pisoT + 10];
    const rod: [number, number] = [cad[0] + (Math.sin(a) * largo) / 2, cad[1] + (Math.cos(a) * largo) / 2];
    const dobla = !e.corre ? rad(-25 * Math.max(0, -signo * e.zancada)) : rad(-45 * Math.abs(e.zancada));
    const pie: [number, number] = [rod[0] + (Math.sin(a + dobla) * largo) / 2, rod[1] + (Math.cos(a + dobla) * largo) / 2];
    const color = signo < 0 ? sombra(p.pantalon) : p.pantalon;
    return (
      <g key={signo}>
        <Miembro pts={[cad, rod, pie]} color={color} ancho={46} />
        <Forma d={`M${pie[0] - 26} ${pie[1] + 26} Q${pie[0] - 26} ${pie[1] - 18} ${pie[0] + 6} ${pie[1] - 18} Q${pie[0] + 58} ${pie[1] - 14} ${pie[0] + 60} ${pie[1] + 26} Z`} fill={ZAPATO} b={7} sd={7}>
          <rect x={pie[0] - 30} y={pie[1] + 16} width={94} height={10} fill="#e9e4dc" />
        </Forma>
      </g>
    );
  });
  const sw = (e.corre ? 34 : 26) * e.zancada;
  const codo = e.corre ? 70 : 25;
  const brazos = [-1, 1].map((signo) => {
    const a1 = rad(signo * sw);
    const x1 = 4 + Math.sin(a1) * L1;
    const y1 = hy + Math.cos(a1) * L1;
    const a2 = a1 + rad(codo);
    const x2 = x1 + Math.sin(a2) * L2;
    const y2 = y1 + Math.cos(a2) * L2;
    const atras = signo < 0;
    return (
      <g key={signo}>
        <Miembro pts={[[4, hy], [x1, y1], [x2, y2]]} color={atras ? sombra(p.ropa) : p.ropa} ancho={36} />
        <Forma d={dCirculo(x2, y2, atras ? 22 : 24)} fill={atras ? sombra(p.piel) : p.piel} b={6} sd={7} />
      </g>
    );
  });
  const pelo = (() => {
    if (p.peinado === 'pelado') return <Forma d={`M${-R + 4} -10 Q${-R - 10} 40 ${-R + 30} 70 Q${-R + 10} 20 ${-R + 30} -20 Z`} fill={p.pelo} b={6} sd={6} />;
    if (p.peinado === 'rulos')
      return (
        <g>
          {([[-70, -80], [-30, -105], [15, -112], [-95, -30], [-100, 25]] as [number, number][]).map(([x, y], i) => (
            <Forma key={i} d={dCirculo(x, y, 40)} fill={p.pelo} b={6} sd={10} brillo={[x - 12, y - 14, 12, 7]} />
          ))}
        </g>
      );
    const lg = p.peinado === 'largo' ? 120 : 40;
    return (
      <Forma d={`M${R - 10} -60 Q${R - 30} ${-R - 20} -10 ${-R - 10} Q${-R - 20} ${-R + 10} ${-R - 6} 10 L${-R + 4} ${lg} Q${-R + 40} ${lg - 30} -40 0 Q0 -50 ${R - 10} -60 Z`} fill={p.pelo} sd={12} brillo={[0, -R + 2, 40, 10]}>
        <Linea d={`M${R - 30} -70 Q20 -110 -60 -100 M${R - 50} -58 Q0 -86 -80 -60`} w={5} o={0.28} />
      </Forma>
    );
  })();
  const cierre = Math.max(0, Math.min(1, e.parpadeo));
  const ojoX = 62;
  const dyCeja = ({arriba: -16, enojo: 2, triste: -6} as Record<string, number>)[e.cejas] ?? 0;
  const ap = Math.max(0, Math.min(1, e.apertura));
  return (
    <g>
      {piernas[0]}
      {brazos[0]}
      {piernas[1]}
      <Forma d={`M-56 ${pisoT} L64 ${pisoT} Q78 ${tope + 60} 50 ${tope + 8} Q0 ${tope - 6} -48 ${tope + 12} Q-66 ${tope + 80} -56 ${pisoT} Z`} fill={p.ropa} sd={18} brillo={[-20, tope + 70, 16, 50]}>
        <rect x={-70} y={pisoT - 34} width={150} height={30} fill={mezclar(p.pantalon, '#000', 0.25)} />
        <Linea d={`M30 ${tope + 30} L46 ${pisoT - 36}`} w={5} o={0.3} />
      </Forma>
      {brazos[1]}
      <g transform={`translate(0 ${cy}) rotate(${e.inclinacion})`}>
        <Forma d={dCirculo(-22, 14, 26)} fill={p.piel} b={6} sd={8} />
        <Forma d={dCirculo(8, 0, R)} fill={p.piel} sd={18} brillo={[-20, -60, 34, 20]} />
        {pelo}
        {p.cachetes ? <ellipse cx={52} cy={40} rx={22} ry={13} fill={P.rosa} opacity={0.42} /> : null}
        {cierre > 0.85 ? (
          <path d={`M${ojoX - 16} -6 Q${ojoX} 4 ${ojoX + 16} -6`} fill="none" stroke={C} strokeWidth={7} strokeLinecap="round" />
        ) : (
          <g>
            <Forma d={dElipse(ojoX, -8, 16, 24 * (1 - cierre))} fill="#fff" b={5} sd={5}>
              <circle cx={ojoX + 6} cy={-5} r={Math.min(11, 24 * (1 - cierre) * 0.6)} fill={iris(p)} />
              <circle cx={ojoX + 7} cy={-5} r={Math.min(6, 24 * (1 - cierre) * 0.35)} fill={C} />
              <circle cx={ojoX + 10} cy={-9} r={3} fill="#fff" />
            </Forma>
            <path d={`M${ojoX - 17} -12 Q${ojoX} ${-34 + 24 * cierre} ${ojoX + 17} -12`} fill="none" stroke={C} strokeWidth={6} strokeLinecap="round" />
          </g>
        )}
        <g transform={`translate(${ojoX} ${-52 + dyCeja}) rotate(${({enojo: 14, triste: -14} as Record<string, number>)[e.cejas] ?? 0})`}>
          <Forma d="M-22 5 Q-4 -12 22 -2 Q20 4 16 4 Q-2 -2 -20 9 Z" fill={mezclar(p.pelo, '#000', 0.25)} b={4} sinSombra />
        </g>
        {p.anteojos ? (
          <g>
            <circle cx={ojoX} cy={-8} r={30} fill="#cdeeff" fillOpacity={0.22} stroke={C} strokeWidth={6} />
            <path d={`M${ojoX - 30} -10 L-10 -14`} stroke={C} strokeWidth={5} />
          </g>
        ) : null}
        <Forma d={dCirculo(R + 6, 22, 22)} fill={mezclar(p.piel, '#e07a5f', 0.15)} b={6} sd={7} brillo={[R, 14, 6, 4]} />
        {p.bigote ? <Forma d={`M${R - 30} 44 Q${R} 34 ${R + 14} 50 Q${R - 6} 62 ${R - 30} 52 Z`} fill={p.pelo} b={5} sd={5} /> : null}
        {e.boca === 'cerrada' || e.boca === 'sonrisa' || ap < 0.08 ? (
          <path d={`M${R - 50} 62 Q${R - 30} ${e.boca === 'sonrisa' ? 74 : 66} ${R - 10} 60`} fill="none" stroke={C} strokeWidth={7} strokeLinecap="round" />
        ) : (
          <Forma d={dElipse(R - 28, 66, 14, 6 + 14 * ap)} fill="#5a1e2a" b={5} sinSombra>
            <rect x={R - 44} y={60 - 6 - 14 * ap} width={32} height={8} fill="#fffaf0" />
          </Forma>
        )}
        <Sombrero p={p} perfil />
      </g>
    </g>
  );
};

export const Persona: React.FC<{p: Personaje; e: Estado}> = ({p, e}) => {
  if (e.perfil) {
    return e.perfil > 0 ? <Perfil p={p} e={e} /> : <g transform="scale(-1 1)"><Perfil p={p} e={e} /></g>;
  }
  return <Frente p={p} e={e} />;
};
