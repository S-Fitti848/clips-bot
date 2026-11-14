// Los lugares con PROFUNDIDAD (Santi, 2026-11-14: "escenarios con perspectiva, no paredes planas"):
// - perspectiva de un punto: techo y paredes laterales en trapecio, piso con tablas/baldosas que fugan
//   al centro y una sombra suave contra la pared;
// - tres planos: lo lejano (cielo, la ciudad por la ventana, las chimeneas) se mueve MENOS con la cámara
//   (parallax), la pared y los muebles van con la cámara, y la viñeta del primer plano encima;
// - la LÍNEA DEL PISO queda donde la puso el motor actual (y ≈ 1382-1420), así los muebles, la tele en su
//   mesa y lo que cae siguen apoyados donde calculó el chequeo de composición.
// La década (semilla = década*100 + variante) cambia la decoración como en escenas.py; las variantes
// impares salen espejadas.
import React from 'react';
import {C, P, Forma, Linea, dCirculo, dElipse, dRect, mezclar, sombra, luz, ANCHO as W, ALTO as H} from './estilo';

type Cam = [number, number, number, number];
type FondoProps = {semilla: number; cam: Cam; t: number};

const rnd = (semilla: number) => {
  let s = (semilla * 9301 + 49297) % 233280 || 1;
  return () => ((s = (s * 16807) % 2147483647) / 2147483647);
};

export const epocaDe = (semilla: number): [number, number] => (semilla >= 1000 ? [Math.floor(semilla / 100), semilla % 100] : [0, semilla]);
const rango = (dec: number) => (!dec || dec >= 200 ? 'hoy' : dec < 195 ? 'antes' : dec < 198 ? 'medio' : 'ochentas');

// Un plano lejano: con la cámara completa ya aplicada afuera, esto deja un movimiento de solo `f`.
export const parallax = ([z, dx, dy]: Cam, f: number) => {
  const zf = 1 + (z - 1) * f;
  const cx = W / 2;
  const cy = H / 2;
  return `translate(${cx + dx} ${cy + dy}) scale(${zf / z}) translate(${-cx - dx * f} ${-cy - dy * f})`;
};

const PISO_Y = H * 0.72; // 1382: la línea del piso contra la pared (igual que escenas.py)
const FUGA: [number, number] = [540, 640];

// ---- la caja de una habitación ------------------------------------------------------------------
const Habitacion: React.FC<{pared: string; piso: string; lineasPiso?: string; baldosas?: boolean; techo?: string; children?: React.ReactNode; dibujo?: React.ReactNode}> = ({pared, piso, lineasPiso, baldosas, techo, children, dibujo}) => {
  const lp = lineasPiso ?? sombra(piso);
  const filas = [1404, 1432, 1468, 1514, 1572, 1646, 1740, 1860];
  return (
    <g>
      <rect x={0} y={0} width={W} height={H} fill={pared} />
      {dibujo}
      {/* luz suave de arriba hacia abajo en la pared */}
      <rect x={0} y={0} width={W} height={PISO_Y} fill="url(#paredLuz)" />
      {/* techo y paredes de costado en perspectiva */}
      <path d={`M0 0 H${W} L${W - 60} 72 H60 Z`} fill={techo ?? mezclar(pared, '#ffffff', 0.25)} />
      <path d={`M0 0 L60 72 V${PISO_Y} L0 ${PISO_Y + 60} Z`} fill={sombra(pared)} />
      <path d={`M${W} 0 L${W - 60} 72 V${PISO_Y} L${W} ${PISO_Y + 60} Z`} fill={mezclar(pared, '#3b2d63', 0.12)} />
      <path d={`M60 72 H${W - 60} M60 72 V${PISO_Y} M${W - 60} 72 V${PISO_Y}`} stroke={C} strokeWidth={4} opacity={0.35} />
      <rect x={60} y={72} width={W - 120} height={16} fill={mezclar(pared, '#ffffff', 0.4)} stroke={C} strokeWidth={3} strokeOpacity={0.4} />
      {/* piso: tablas o baldosas que fugan al centro */}
      <path d={`M60 ${PISO_Y} H${W - 60} L${W} ${PISO_Y + 60} V${H} H0 V${PISO_Y + 60} Z`} fill={piso} />
      <g opacity={0.55}>
        {Array.from({length: 15}, (_, i) => {
          const xb = 60 + (i * (W - 120)) / 14;
          const k = (H - FUGA[1]) / (PISO_Y - FUGA[1]);
          const xa = FUGA[0] + (xb - FUGA[0]) * k;
          return <path key={i} d={`M${xb} ${PISO_Y} L${xa} ${H}`} stroke={lp} strokeWidth={4} />;
        })}
        {filas.map((y, i) => (
          <path key={'f' + i} d={`M0 ${y} H${W}`} stroke={lp} strokeWidth={baldosas ? 4 : 2.5} strokeDasharray={baldosas ? undefined : `${120 + i * 30} ${40 + i * 10}`} strokeDashoffset={i * 57} />
        ))}
      </g>
      <rect x={0} y={PISO_Y} width={W} height={H - PISO_Y} fill="url(#pisoSombra)" />
      {/* zócalo */}
      <path d={`M60 ${PISO_Y - 30} H${W - 60} V${PISO_Y} H60 Z`} fill={P.blanco} stroke={C} strokeWidth={4} />
      <path d={`M0 ${PISO_Y + 30} L60 ${PISO_Y - 30} V${PISO_Y} L0 ${PISO_Y + 60} Z M${W} ${PISO_Y + 30} L${W - 60} ${PISO_Y - 30} V${PISO_Y} L${W} ${PISO_Y + 60} Z`} fill={sombra(P.blanco)} stroke={C} strokeWidth={4} />
      {children}
    </g>
  );
};

// Una ventana con lo de afuera en un plano lejano (parallax) y el reflejo del vidrio.
const Ventana: React.FC<{x: number; y: number; w: number; h: number; cam: Cam; t: number; afuera?: 'cielo' | 'ciudad' | 'fabrica'; marco?: string}> = ({x, y, w, h, cam, t, afuera = 'cielo', marco = P.blanco}) => {
  const id = `v${x}_${y}`;
  return (
    <g>
      <clipPath id={id}>
        <rect x={x} y={y} width={w} height={h} />
      </clipPath>
      <g clipPath={`url(#${id})`}>
        <g transform={parallax(cam, 0.35)}>
          <rect x={x - 200} y={y - 200} width={w + 400} height={h + 400} fill="url(#cieloDeg)" />
          <circle cx={x + w * 0.75} cy={y + h * 0.25} r={40} fill="#fff1a6" />
          <g transform={`translate(${((t * 12) % (w + 300)) - 150} 0)`}>
            <Nube x={x + w * 0.3} y={y + h * 0.3} s={0.45} />
          </g>
          {afuera === 'cielo' ? (
            <path d={`M${x - 200} ${y + h} Q${x + w * 0.3} ${y + h * 0.55} ${x + w * 0.6} ${y + h * 0.8} Q${x + w * 0.9} ${y + h * 0.6} ${x + w + 200} ${y + h * 0.75} V${y + h + 200} H${x - 200} Z`} fill="#9ad97f" stroke={C} strokeWidth={4} />
          ) : afuera === 'ciudad' ? (
            Array.from({length: 7}, (_, i) => (
              <rect key={i} x={x - 100 + i * 90} y={y + h * (0.35 + ((i * 37) % 5) * 0.08)} width={80} height={h} fill={i % 2 ? '#a9b8e8' : '#8d9fd8'} stroke={C} strokeWidth={4} />
            ))
          ) : (
            [0, 1, 2].map((i) => (
              <g key={i}>
                <rect x={x + 60 + i * (w / 3)} y={y + h * (0.3 + (i % 2) * 0.12)} width={56} height={h} fill={P.grisOscuro} stroke={C} strokeWidth={4} />
                <Nube x={x + 88 + i * (w / 3) + Math.sin(t + i) * 10} y={y + h * (0.22 + (i % 2) * 0.12) - ((t * 20 + i * 30) % 60)} s={0.3} />
              </g>
            ))
          )}
        </g>
        <path d={`M${x} ${y + h * 0.15} L${x + w * 0.25} ${y} H${x + w * 0.4} L${x} ${y + h * 0.4} Z`} fill="#fff" opacity={0.35} />
      </g>
      <rect x={x} y={y} width={w} height={h} fill="none" stroke={C} strokeWidth={22} />
      <rect x={x} y={y} width={w} height={h} fill="none" stroke={marco} strokeWidth={12} />
      <path d={`M${x + w / 2} ${y} V${y + h} M${x} ${y + h / 2} H${x + w}`} stroke={C} strokeWidth={16} />
      <path d={`M${x + w / 2} ${y} V${y + h} M${x} ${y + h / 2} H${x + w}`} stroke={marco} strokeWidth={8} />
      <Forma d={dRect(x - 24, y + h, w + 48, 22, 4)} fill={marco} b={5} sd={6} />
    </g>
  );
};

export const Nube: React.FC<{x: number; y: number; s?: number}> = ({x, y, s = 1}) => (
  <g transform={`translate(${x} ${y}) scale(${s})`}>
    <Forma d="M-120 40 Q-150 40 -150 10 Q-150 -24 -112 -26 Q-104 -78 -48 -74 Q-20 -112 30 -90 Q78 -102 92 -52 Q146 -54 148 -6 Q150 40 110 40 Z" fill="#ffffff" b={6} sd={18} />
  </g>
);

const Cortina: React.FC<{x: number; y: number; h: number; color: string; lado: number; t: number}> = ({x, y, h, color, lado, t}) => {
  const vaiven = Math.sin(t * 1.3 + lado) * 4;
  const d = `M${x} ${y - 14} L${x + 76} ${y - 14} Q${x + 40 + vaiven} ${y + h * 0.5} ${x + 70 + vaiven} ${y + h + 30} L${x + 6 + vaiven} ${y + h + 30} Q${x - 6} ${y + h * 0.5} ${x} ${y - 14} Z`;
  return (
    <Forma d={d} fill={color} b={6} sd={14}>
      {[16, 34, 52].map((k) => (
        <path key={k} d={`M${x + k} ${y} Q${x + k - 6 + vaiven} ${y + h * 0.5} ${x + k + 4 + vaiven} ${y + h + 20}`} fill="none" stroke={sombra(color)} strokeWidth={7} />
      ))}
    </Forma>
  );
};

const Libros: React.FC<{x: number; y: number; ancho: number; semilla: number}> = ({x, y, ancho, semilla}) => {
  const r = rnd(semilla);
  const cs = [P.rojo, P.azul, P.verde, P.amarillo, P.violeta, P.naranja, P.turquesa];
  const out: React.ReactNode[] = [];
  let cx = x;
  let i = 0;
  while (cx < x + ancho - 20) {
    const [w, h] = [[18, 70], [22, 80], [16, 62], [26, 74]][Math.floor(r() * 4)];
    const c = cs[Math.floor(r() * cs.length)];
    const incl = r() < 0.12 && cx > x + 20 ? -8 : 0;
    out.push(
      <g key={i++} transform={`rotate(${incl} ${cx} ${y})`}>
        <rect x={cx} y={y - h} width={w} height={h} rx={2} fill={c} stroke={C} strokeWidth={3.5} />
        <rect x={cx + w * 0.6} y={y - h + 2} width={w * 0.35} height={h - 4} fill={sombra(c)} />
        <rect x={cx + 3} y={y - h + 10} width={w - 6} height={5} fill={luz(c)} />
      </g>,
    );
    cx += w + 2;
  }
  return <g>{out}</g>;
};

const ObjetoEpoca: React.FC<{dec: number; x: number; y: number}> = ({dec, x, y}) => {
  const r = rango(dec);
  if (r === 'antes')
    return (
      <g>
        <Forma d={dRect(x - 50, y - 50, 100, 50, 6)} fill={P.madera} b={6} sd={8} />
        <Forma d={`M${x} ${y - 50} L${x + 10} ${y - 110} Q${x + 70} ${y - 190} ${x + 90} ${y - 120} Q${x + 40} ${y - 110} ${x + 20} ${y - 60} Z`} fill="#c9a24a" b={6} sd={10} brillo={[x + 50, y - 150, 10, 6]} />
      </g>
    );
  if (r === 'medio')
    return (
      <g>
        <Forma d={dRect(x - 80, y - 90, 120, 90, 18)} fill="#a0522d" sd={10} brillo={[x - 50, y - 80, 20, 5]}>
          <circle cx={x - 50} cy={y - 45} r={26} fill="#e9d8a6" stroke={C} strokeWidth={4} />
          <rect x={x - 18} y={y - 70} width={44} height={50} fill="#e9d8a6" stroke={C} strokeWidth={4} />
        </Forma>
        <Forma d={dRect(x + 50, y - 40, 70, 40, 10)} fill="#2b2b33" b={6} sd={6} />
        <Forma d={dCirculo(x + 85, y - 30, 16)} fill="#ddd" b={4} sd={4} />
      </g>
    );
  if (r === 'ochentas')
    return (
      <Forma d={dRect(x - 90, y - 70, 180, 70, 8)} fill="#5b6170" sd={10}>
        <circle cx={x - 55} cy={y - 35} r={22} fill="#2b2b33" stroke={C} strokeWidth={4} />
        <circle cx={x + 55} cy={y - 35} r={22} fill="#2b2b33" stroke={C} strokeWidth={4} />
        <rect x={x - 22} y={y - 55} width={44} height={28} fill="#9fe3ff" stroke={C} strokeWidth={3} />
      </Forma>
    );
  return (
    <g>
      <Forma d={dRect(x - 30, y - 70, 60, 70, 10)} fill={P.turquesa} b={6} sd={8} />
      <Forma d={dCirculo(x, y - 90, 30)} fill={P.verde} b={6} sd={8} />
    </g>
  );
};

const Planta: React.FC<{x: number; y: number; t: number; s?: number}> = ({x, y, t, s = 1}) => (
  <g transform={`translate(${x} ${y}) scale(${s})`}>
    {[-40, -15, 10, 35].map((a, i) => (
      <g key={a} transform={`rotate(${a + Math.sin(t * 1.1 + i) * 1.5})`}>
        <Forma d="M0 0 Q-30 -90 0 -170 Q30 -90 0 0 Z" fill={i % 2 ? P.verde : mezclar(P.verde, '#1f6b3a', 0.3)} b={5} sd={8}>
          <Linea d="M0 -10 Q-4 -90 0 -160" w={3} o={0.35} />
        </Forma>
      </g>
    ))}
    <Forma d="M-60 0 L60 0 L48 130 L-48 130 Z" fill={P.naranja} sd={12} brillo={[-34, 30, 6, 30]} />
    <rect x={-66} y={-6} width={132} height={22} rx={6} fill={mezclar(P.naranja, '#000', 0.12)} stroke={C} strokeWidth={5} />
  </g>
);

// ---- los lugares -----------------------------------------------------------------------------------
const ESTILOS_CASA: Record<number, [string, string, string, [string, string], string]> = {
  0: ['#eef1f4', '#e3e8ee', '#7b8fa6', ['#9aa5b1', '#d5dbe1'], '#c9d6e3'],
  190: ['#d8c9a3', '#c9b88d', '#8e2c2c', ['#8e2c2c', '#d9a441'], '#7a1f2b'],
  195: ['#f7d9a0', '#e8b96a', '#2a9d8f', ['#e76f51', '#f4a261'], '#e76f51'],
  196: ['#f2b25c', '#c9762e', '#e9c46a', ['#bc6c25', '#dda15e'], '#bc4749'],
  197: ['#c99a5b', '#8a5a2b', '#a3542b', ['#6b4226', '#d4a373'], '#606c38'],
  198: ['#f6d6e6', '#9fd8d0', '#7fc8f8', ['#ff99c8', '#fcf6bd'], '#a9def9'],
  199: ['#e4ecd5', '#c3d7a4', '#5e8c61', ['#8fa38a', '#dfe8cc'], '#5e8c61'],
};
const estiloCasa = (dec: number) => (!dec || dec >= 200 ? ESTILOS_CASA[0] : dec < 195 ? ESTILOS_CASA[190] : ESTILOS_CASA[dec] ?? ESTILOS_CASA[196]);

const Casa: React.FC<FondoProps> = ({semilla, cam, t}) => {
  const [dec, variante] = epocaDe(semilla);
  const [pared, dibujo, sillon, [alf1, alf2], cortina] = estiloCasa(dec);
  const hoy = !dec || dec >= 200;
  const papel = (() => {
    if (dec && dec < 195)
      return (
        <g>
          {Array.from({length: 12}, (_, j) =>
            Array.from({length: 10}, (_, i) => <circle key={`${i}_${j}`} cx={40 + i * 110 + (j % 2) * 55} cy={110 + j * 110} r={9} fill={dibujo} />),
          )}
          <rect x={60} y={H * 0.5} width={W - 120} height={PISO_Y - H * 0.5} fill="#8a6a45" />
          {Array.from({length: 6}, (_, i) => <Forma key={i} d={dRect(90 + i * 160, H * 0.52, 130, H * 0.17, 6)} fill="#9c7b52" b={4} sd={8} />)}
        </g>
      );
    if (dec && dec < 198)
      return (
        <g>
          {Array.from({length: 8}, (_, j) =>
            Array.from({length: 7}, (_, i) => (
              <g key={`${i}_${j}`}>
                <circle cx={60 + i * 170 + (j % 2) * 85} cy={150 + j * 170} r={34} fill={dibujo} />
                <circle cx={60 + i * 170 + (j % 2) * 85} cy={150 + j * 170} r={16} fill={pared} />
              </g>
            )),
          )}
        </g>
      );
    if (dec && dec < 200)
      return (
        <g>
          {Array.from({length: 9}, (_, j) => (
            <path key={j} d={'M0 ' + (150 + j * 140) + ' ' + Array.from({length: 20}, (_, i) => `L${i * 60} ${150 + j * 140 + (i % 2 ? 28 : 0)}`).join(' ')} fill="none" stroke={dibujo} strokeWidth={12} />
          ))}
        </g>
      );
    return <rect x={60} y={H * 0.36} width={W - 120} height={14} fill={dibujo} />;
  })();
  return (
    <Habitacion pared={pared} piso={dec ? '#b98a5e' : '#c8a27a'} dibujo={papel}>
      {/* luz de la ventana sobre el piso */}
      <path d="M640 580 L940 580 L1080 1760 L470 1660 Z" fill="url(#luzVentana)" />
      <Ventana x={640} y={250} w={300} h={330} cam={cam} t={t} />
      <rect x={610} y={220} width={360} height={18} rx={6} fill={P.madera} stroke={C} strokeWidth={4} />
      <Cortina x={614} y={250} h={330} color={cortina} lado={0} t={t} />
      <Cortina x={890} y={250} h={330} color={cortina} lado={1} t={t} />
      {/* biblioteca */}
      <Forma d={dRect(30, 330, 200, 1050, 6)} fill={P.madera} sd={16} brillo={[50, 600, 5, 300]}>
        <rect x={44} y={344} width={172} height={1022} fill={sombra(P.madera)} />
      </Forma>
      {[520, 760, 1000, 1240].map((y, k) => (
        <g key={y}>
          <Forma d={dRect(42, y, 176, 16)} fill={P.maderaOscura} b={4} sd={4} />
          <Libros x={48} y={y} ancho={166} semilla={semilla * 7 + k} />
        </g>
      ))}
      <ObjetoEpoca dec={dec} x={130} y={330} />
      {hoy ? (
        <g>
          <Forma d={dRect(300, 330, 220, 160, 4)} fill={P.blanco} sd={10} />
          <rect x={318} y={348} width={184} height={124} fill="#7fb7e8" stroke={C} strokeWidth={4} />
          <circle cx={380} cy={410} r={30} fill={P.amarillo} stroke={C} strokeWidth={4} />
          <rect x={420} y={380} width={60} height={70} fill={P.rojo} stroke={C} strokeWidth={4} />
        </g>
      ) : (
        <g>
          <Forma d={dElipse(410, 410, 90, 110)} fill="#c9a24a" sd={12} brillo={[370, 340, 12, 20]} />
          <Forma d={dElipse(410, 410, 70, 88)} fill="#efe2c1" b={5} sd={8}>
            <circle cx={410} cy={390} r={28} fill="#6b4a2e" stroke={C} strokeWidth={4} />
            <ellipse cx={410} cy={470} rx={44} ry={30} fill="#6b4a2e" stroke={C} strokeWidth={4} />
          </Forma>
        </g>
      )}
      {/* alfombra en perspectiva */}
      <Forma d={dElipse(W / 2, H * 0.86, 420, 90)} fill={alf1} b={6} sd={14}>
        <ellipse cx={W / 2} cy={H * 0.86} rx={340} ry={62} fill={alf2} />
        {dec && dec < 200 ? <ellipse cx={W / 2} cy={H * 0.86} rx={220} ry={36} fill={alf1} /> : null}
        <ellipse cx={W / 2} cy={H * 0.86} rx={380} ry={76} fill="none" stroke={luz(alf1)} strokeWidth={4} strokeDasharray="10 12" />
      </Forma>
      {/* sillón con volumen: respaldo, asiento, almohadones, patas */}
      {dec && dec >= 195 && dec < 198
        ? [580, 1000].map((x) => <Forma key={x} d={`M${x} 1305 L${x + 14} 1305 L${x + 6} 1380 L${x + 2} 1380 Z`} fill={P.madera} b={4} sd={3} />)
        : [575, 1005].map((x) => <Forma key={x} d={dRect(x - 15, 1300, 30, 60, 4)} fill={P.madera} b={5} sd={5} />)}
      <Forma d={dRect(560, 1050, 460, 200, 40)} fill={sombra(sillon)} sd={18} />
      <Forma d={dRect(600, 1080, 190, 120, 30)} fill={sillon} b={5} sd={14} brillo={[640, 1100, 30, 10]} />
      <Forma d={dRect(800, 1080, 190, 120, 30)} fill={sillon} b={5} sd={14} brillo={[840, 1100, 30, 10]} />
      <Forma d={dRect(530, 1150, 520, 160, 40)} fill={sillon} sd={20} brillo={[600, 1170, 60, 10]}>
        <Linea d="M790 1170 Q792 1230 788 1300" w={4} o={0.3} />
      </Forma>
      <Forma d={dRect(510, 1120, 70, 190, 30)} fill={sillon} b={6} sd={14} />
      <Forma d={dRect(1000, 1120, 70, 190, 30)} fill={sillon} b={6} sd={14} />
      <Forma d={dRect(600, 1090, 110, 80, 24)} fill={cortina} b={5} sd={10} />
      {variante % 3 !== 2
        ? ([[820, 1440, P.rojo], [880, 1440, P.azul], [850, 1388, P.amarillo]] as [number, number, string][]).map(([x, y, c]) => (
            <g key={`${x}${y}`}>
              <path d={`M${x} ${y} l10 -10 h56 l-10 10 Z`} fill={luz(c)} stroke={C} strokeWidth={4} />
              <path d={`M${x + 56} ${y} l10 -10 v56 l-10 10 Z`} fill={sombra(c)} stroke={C} strokeWidth={4} />
              <Forma d={dRect(x, y, 56, 56, 4)} fill={c} b={5} sd={6} />
            </g>
          ))
        : null}
      {hoy ? <Planta x={1010} y={1260} t={t} s={0.75} /> : null}
    </Habitacion>
  );
};

const Taller: React.FC<FondoProps> = ({cam, t}) => (
  <Habitacion pared="#c7b299" piso="#8d6e63" dibujo={
    <g>
      {Array.from({length: 26}, (_, i) => <path key={i} d={`M60 ${90 + i * 50} H${W - 60}`} stroke="#a8916f" strokeWidth={3} />)}
    </g>
  }>
    <Ventana x={760} y={120} w={220} h={170} cam={cam} t={t} afuera="cielo" marco="#8d6e63" />
    <Forma d={dRect(80, 300, 640, 440, 8)} fill="#a1887f" sd={14}>
      {Array.from({length: 10}, (_, i) => Array.from({length: 7}, (_, j) => <circle key={`${i}_${j}`} cx={120 + i * 60} cy={340 + j * 60} r={6} fill="#6d4c41" />))}
    </Forma>
    {/* herramientas colgadas */}
    <g transform="translate(220 470) rotate(-30) scale(0.7)">
      <Forma d={dRect(-12, -40, 24, 200, 8)} fill={P.madera} b={6} sd={6} />
      <Forma d="M-70 -90 L70 -90 L74 -60 L70 -30 L-70 -30 Z" fill={P.grisOscuro} sd={10} />
    </g>
    <g transform="translate(400 500) rotate(20)">
      <Forma d="M-14 -120 L14 -120 L14 60 Q30 70 30 100 L14 120 L14 96 L-14 96 L-14 120 L-30 100 Q-30 70 -14 60 Z" fill={P.gris} sd={8} brillo={[-6, -60, 3, 40]} />
    </g>
    <g transform={`translate(590 470) rotate(${(t * 25) % 360})`}>
      {Array.from({length: 8}, (_, i) => <g key={i} transform={`rotate(${i * 45})`}><Forma d={dRect(-14, -74, 28, 32, 4)} fill={P.gris} b={5} sd={4} /></g>)}
      <Forma d={dCirculo(0, 0, 56)} fill={P.gris} sd={12} brillo={[-20, -24, 12, 6]} />
      <Forma d={dCirculo(0, 0, 18)} fill={P.blanco} b={5} sd={4} />
    </g>
    {/* plano azul */}
    <Forma d={dRect(760, 360, 240, 300, 6)} fill="#bbdefb" sd={10}>
      <Linea d="M790 420 L960 420 M790 480 L920 480 M790 540 L960 540" w={6} o={0.6} color="#3a6ea5" />
      <circle cx={880} cy={600} r={40} fill="none" stroke="#3a6ea5" strokeWidth={6} />
    </Forma>
    {/* lámpara colgante con su cono de luz */}
    <path d="M400 72 V180" stroke={C} strokeWidth={5} />
    <path d="M330 230 L470 230 L760 1380 L60 1380 Z" fill="#fff3b0" opacity={0.12} />
    <Forma d="M340 230 Q400 160 460 230 Z" fill={P.verde} b={6} sd={10} />
    <circle cx={400} cy={232} r={16} fill="#fff6c0" stroke={C} strokeWidth={4} />
    {/* banco de trabajo con tapa en perspectiva */}
    <Forma d={dRect(100, H * 0.62 + 44, 50, 300, 4)} fill={sombra(P.madera)} b={6} sd={8} />
    <Forma d={dRect(930, H * 0.62 + 44, 50, 300, 4)} fill={sombra(P.madera)} b={6} sd={8} />
    <path d={`M90 ${H * 0.62} L990 ${H * 0.62} L1020 ${H * 0.62 + 50} L60 ${H * 0.62 + 50} Z`} fill={luz(P.madera)} stroke={C} strokeWidth={5} />
    <Forma d={dRect(60, H * 0.62 + 44, 960, 34, 4)} fill={P.madera} sd={10} />
    <Forma d={dRect(200, H * 0.62 - 70, 140, 70, 8)} fill={P.rojo} sd={12} brillo={[220, H * 0.62 - 60, 30, 5]}>
      <rect x={250} y={H * 0.62 - 80} width={40} height={14} fill={P.grisOscuro} />
    </Forma>
  </Habitacion>
);

const Oficina: React.FC<FondoProps> = ({semilla, cam, t}) => {
  const [dec] = epocaDe(semilla);
  const viejo = dec && dec < 199;
  const y0 = H * 0.62;
  return (
    <Habitacion pared="#f3e3c3" piso="#c79a6b">
      <path d="M560 740 L960 740 L1080 1500 L420 1450 Z" fill="url(#luzVentana)" />
      <Ventana x={560} y={260} w={400} h={480} cam={cam} t={t} afuera="ciudad" />
      <Forma d={dRect(120, 330, 280, 210, 6)} fill={P.blanco} sd={10}>
        <path d="M150 510 L230 400 L290 470 L330 430 L380 510 Z" fill={P.verde} stroke={C} strokeWidth={4} />
        <circle cx={330} cy={380} r={22} fill={P.amarillo} stroke={C} strokeWidth={4} />
      </Forma>
      {/* archivero */}
      <Forma d={dRect(760, 900, 160, 480, 6)} fill={P.gris} sd={14} brillo={[780, 920, 5, 200]}>
        {[960, 1110, 1260].map((y) => (
          <g key={y}>
            <rect x={780} y={y - 40} width={120} height={120} fill="none" stroke={C} strokeWidth={4} opacity={0.5} />
            <rect x={815} y={y} width={50} height={12} rx={5} fill={P.grisOscuro} />
          </g>
        ))}
      </Forma>
      <Forma d={dRect(110, y0 + 40, 40, 280, 3)} fill={sombra(P.madera)} b={6} sd={6} />
      <Forma d={dRect(630, y0 + 40, 40, 280, 3)} fill={sombra(P.madera)} b={6} sd={6} />
      <path d={`M100 ${y0 - 20} L680 ${y0 - 20} L700 ${y0} L80 ${y0} Z`} fill={luz(P.madera)} stroke={C} strokeWidth={5} />
      <Forma d={dRect(80, y0, 620, 46, 6)} fill={P.madera} sd={12} />
      {viejo ? (
        <g>
          <Forma d={dRect(300, y0 - 150, 170, 70)} fill={P.blanco} b={5} sd={6}>
            <Linea d={`M320 ${y0 - 130} H450 M320 ${y0 - 112} H430`} w={3} o={0.5} />
          </Forma>
          <Forma d={dRect(270, y0 - 90, 230, 90, 14)} fill="#3d4250" sd={14} brillo={[300, y0 - 80, 40, 6]} />
          {Array.from({length: 5}, (_, k) => <Forma key={k} d={dCirculo(300 + k * 40, y0 - 30, 12)} fill="#cfd3da" b={4} sd={4} />)}
          <Forma d={dRect(560, y0 - 60, 110, 60, 14)} fill="#2b2b33" sd={8} />
          <Forma d={dCirculo(615, y0 - 34, 20)} fill="#ddd" b={4} sd={5} />
        </g>
      ) : (
        <g>
          <Forma d={dRect(365, y0 - 22, 40, 24)} fill={P.grisOscuro} b={5} sd={4} />
          <Forma d={dRect(260, y0 - 190, 250, 170, 10)} fill={P.grisOscuro} sd={12} />
          <rect x={278} y={y0 - 172} width={214} height={134} rx={4} fill="#9fe3ff" stroke={C} strokeWidth={4} />
          <path d={`M290 ${y0 - 160} L330 ${y0 - 160} L290 ${y0 - 120} Z`} fill="#fff" opacity={0.6} />
        </g>
      )}
      <Planta x={920} y={H * 0.66 + 40} t={t} s={0.8} />
    </Habitacion>
  );
};

const Fabrica: React.FC<FondoProps> = ({semilla, cam, t}) => {
  const [dec] = epocaDe(semilla);
  const r = rango(dec);
  const y = H * 0.66;
  return (
    <Habitacion pared="#d9dde6" piso="#8a8f9c" baldosas>
      <Ventana x={80} y={200} w={920} h={420} cam={cam} t={t} afuera="fabrica" marco="#9aa0ab" />
      {/* caño rojo con remaches y engranajes que giran */}
      <Forma d={dRect(60, 700, W - 120, 34)} fill={P.rojo} sd={10} brillo={[300, 706, 200, 4]}>
        {Array.from({length: 12}, (_, i) => <circle key={i} cx={100 + i * 80} cy={717} r={5} fill={sombra(P.rojo)} />)}
      </Forma>
      {([[170, 90, 1], [330, 60, -1.5], [880, 110, 0.8]] as [number, number, number][]).map(([x, rr, v]) => (
        <g key={x} transform={`translate(${x} 900) scale(${rr / 100}) rotate(${(t * 40 * v) % 360})`}>
          {Array.from({length: 8}, (_, i) => <g key={i} transform={`rotate(${i * 45})`}><Forma d={dRect(-22, -122, 44, 54, 6)} fill={P.gris} b={6} sd={6} /></g>)}
          <Forma d={dCirculo(0, 0, 90)} fill={P.gris} sd={16} brillo={[-34, -40, 18, 10]} />
          <Forma d={dCirculo(0, 0, 30)} fill={P.blanco} b={6} sd={6} />
        </g>
      ))}
      {/* máquina de la época */}
      {r === 'antes' ? (
        <g>
          <Forma d={dRect(770, 760, 240, 380, 60)} fill="#8d6e63" sd={20} brillo={[810, 800, 14, 120]} />
          <Forma d={dCirculo(890, 860, 50)} fill="#e9d8a6" b={6} sd={8} />
          <path d={`M890 860 L${890 + Math.cos(t * 3) * 34} ${860 + Math.sin(t * 3) * 34}`} stroke={C} strokeWidth={6} strokeLinecap="round" />
          <Forma d={dRect(840, 1140, 100, 40)} fill="#5d4037" b={6} sd={6} />
        </g>
      ) : r === 'hoy' ? (
        <g>
          <Forma d={dRect(780, 760, 240, 160, 10)} fill="#2b2b33" sd={12} />
          <rect x={800} y={780} width={200} height={120} fill="#3fd1a8" stroke={C} strokeWidth={4} />
          <path d={`M900 1180 L860 1040 L${960 + Math.sin(t * 2) * 20} ${980 + Math.cos(t * 2) * 10}`} fill="none" stroke={C} strokeWidth={48} strokeLinecap="round" strokeLinejoin="round" />
          <path d={`M900 1180 L860 1040 L${960 + Math.sin(t * 2) * 20} ${980 + Math.cos(t * 2) * 10}`} fill="none" stroke={P.naranja} strokeWidth={34} strokeLinecap="round" strokeLinejoin="round" />
          <Forma d={dRect(840, 1160, 120, 40, 6)} fill={P.grisOscuro} b={6} sd={6} />
        </g>
      ) : (
        <g>
          <Forma d={dRect(800, 780, 180, 240, 10)} fill={P.gris} sd={14} />
          <Forma d={dCirculo(890, 850, 50)} fill={P.blanco} b={5} sd={6} />
          <path d="M890 850 L890 815 M890 850 L915 860" stroke={C} strokeWidth={6} />
          {[P.rojo, P.verde, P.amarillo].map((c, k) => (
            <g key={c}>
              <Forma d={dRect(800 + k * 60, 1060, 22, 90)} fill={P.grisOscuro} b={4} sd={4} />
              <Forma d={dCirculo(811 + k * 60, 1060, 18)} fill={c} b={4} sd={5} />
            </g>
          ))}
        </g>
      )}
      {/* cinta transportadora: los rodillos giran */}
      <Forma d={dRect(40, y, W - 80, 60, 30)} fill={P.grisOscuro} sd={12} />
      {Array.from({length: 9}, (_, i) => (
        <g key={i} transform={`translate(${90 + i * 112} ${y + 30}) rotate(${(t * 180) % 360})`}>
          <circle r={18} fill={P.gris} stroke={C} strokeWidth={5} />
          <path d="M-12 0 H12" stroke={C} strokeWidth={4} />
        </g>
      ))}
      {[60, 360, 660].map((x) => (
        <g key={x}>
          <path d={`M${x} ${y - 130} l20 -16 h150 l-20 16 Z`} fill={luz(P.madera)} stroke={C} strokeWidth={4} />
          <Forma d={dRect(x, y - 130, 150, 130, 6)} fill={P.madera} sd={12}>
            <path d={`M${x} ${y - 95} H${x + 150}`} stroke={C} strokeWidth={4} opacity={0.5} />
          </Forma>
        </g>
      ))}
    </Habitacion>
  );
};

const Tienda: React.FC<FondoProps> = ({semilla, t}) => {
  const [dec] = epocaDe(semilla);
  const r = rango(dec);
  const ran = rnd(semilla + 3);
  const cs = [P.rojo, P.azul, P.verde, P.amarillo, P.naranja, P.violeta, P.rosa, P.turquesa];
  return (
    <Habitacion pared="#fff3dc" piso="#e9c9a0" baldosas lineasPiso="#c9a77c">
      {[60, 560].map((x0) => (
        <g key={x0}>
          <Forma d={dRect(x0, 260, 460, 1120, 10)} fill="#b98a5e" sd={16}>
            <rect x={x0 + 14} y={274} width={432} height={1092} fill={sombra('#b98a5e')} />
          </Forma>
          {[0, 1, 2, 3].map((k) => {
            const ye = 300 + k * 270;
            const items: React.ReactNode[] = [];
            let x = x0 + 30;
            let i = 0;
            while (x < x0 + 410) {
              const [w, h] = [[60, 150], [80, 110], [50, 180], [90, 90]][Math.floor(ran() * 4)];
              if (x + w > x0 + 435) break;
              const c = cs[Math.floor(ran() * cs.length)];
              items.push(
                h > 140 ? (
                  <Forma key={i++} d={`M${x + w * 0.35} ${ye + 200 - h} L${x + w * 0.65} ${ye + 200 - h} L${x + w * 0.65} ${ye + 230 - h} Q${x + w} ${ye + 250 - h} ${x + w} ${ye + 280 - h} L${x + w} ${ye + 200} L${x} ${ye + 200} L${x} ${ye + 280 - h} Q${x} ${ye + 250 - h} ${x + w * 0.35} ${ye + 230 - h} Z`} fill={c} b={4} sd={8} brillo={[x + w * 0.25, ye + 220 - h * 0.4, 4, 20]} />
                ) : (
                  <Forma key={i++} d={dRect(x, ye + 200 - h, w, h, 6)} fill={c} b={4} sd={8}>
                    <rect x={x + 8} y={ye + 200 - h * 0.65} width={w - 16} height={h * 0.3} fill={P.blanco} />
                  </Forma>
                ),
              );
              x += w + 14;
            }
            return (
              <g key={k}>
                {items}
                <Forma d={dRect(x0 + 20, ye + 200, 420, 26, 4)} fill={P.madera} b={5} sd={6} />
              </g>
            );
          })}
        </g>
      ))}
      <g transform={`translate(860 150) scale(0.7) rotate(${Math.sin(t * 1.5) * 2})`}>
        <Forma d={dRect(-190, -140, 380, 170, 14)} fill={P.amarillo} sd={14} />
        <text x={0} y={-36} fontFamily="'DejaVu Sans', sans-serif" fontWeight={900} fontSize={64} textAnchor="middle" fill={C} stroke={P.blanco} strokeWidth={6} paintOrder="stroke">OFERTA</text>
      </g>
      {/* mostrador y la caja de la época */}
      <path d="M40 1240 L340 1240 L360 1260 L60 1260 Z" fill={luz(r !== 'hoy' ? '#8a5a2b' : '#cfd8dc')} stroke={C} strokeWidth={5} />
      <Forma d={dRect(40, 1260, 300, 160, 6)} fill={r !== 'hoy' ? '#8a5a2b' : '#cfd8dc'} sd={14} />
      {r === 'antes' ? (
        <g>
          <Forma d="M100 1260 L110 1170 L250 1170 L270 1260 Z" fill="#c9a24a" sd={10} brillo={[130, 1190, 20, 10]} />
          <Forma d={dRect(130, 1150, 110, 30)} fill="#e9d8a6" b={5} sd={5} />
        </g>
      ) : r === 'hoy' ? (
        <g>
          <Forma d={dRect(120, 1140, 140, 100, 8)} fill="#2b2b33" sd={10} />
          <rect x={132} y={1152} width={116} height={76} fill="#3fd1a8" stroke={C} strokeWidth={4} />
        </g>
      ) : (
        <g>
          <Forma d={dRect(110, 1170, 160, 90, 8)} fill={P.gris} sd={10} />
          <Forma d={dRect(130, 1140, 120, 34)} fill="#2b2b33" b={5} sd={5} />
          {Array.from({length: 5}, (_, k) => <circle key={k} cx={130 + k * 30} cy={1210} r={9} fill={P.blanco} stroke={C} strokeWidth={3} />)}
        </g>
      )}
    </Habitacion>
  );
};

const Auto: React.FC<{r: string; color: string}> = ({r, color}) => {
  const ruedas = (
    <g>
      {[-110, 110].map((x) => (
        <g key={x}>
          <Forma d={dCirculo(x, 40, 36)} fill="#2b2b33" sd={8} />
          <Forma d={dCirculo(x, 40, 14)} fill={P.gris} b={4} sd={4} />
        </g>
      ))}
    </g>
  );
  const vidrio = '#9fe3ff';
  if (r === 'antes')
    return (
      <g>
        <Forma d="M-170 30 L-170 -40 L-90 -40 L-80 -140 L80 -140 L90 -40 L170 -40 L170 30 Z" fill={color} sd={16} brillo={[-60, -120, 30, 6]}>
          <rect x={-60} y={-124} width={50} height={70} fill={vidrio} stroke={C} strokeWidth={4} />
          <rect x={10} y={-124} width={50} height={70} fill={vidrio} stroke={C} strokeWidth={4} />
        </Forma>
        <Forma d={dRect(-190, 20, 380, 14, 6)} fill="#2b2b33" b={4} sd={3} />
        {ruedas}
      </g>
    );
  if (r === 'medio')
    return (
      <g>
        <Forma d="M-200 30 Q-210 -30 -150 -40 L-90 -44 Q-60 -110 20 -110 Q90 -110 110 -44 L180 -40 L210 -70 L210 30 Z" fill={color} sd={16} brillo={[-120, -30, 60, 6]}>
          <path d="M-70 -46 Q-50 -96 0 -96 L0 -46 Z M10 -46 L10 -96 Q70 -96 92 -46 Z" fill={vidrio} stroke={C} strokeWidth={4} />
        </Forma>
        <Forma d={dRect(-200, 10, 410, 12, 6)} fill={P.gris} b={4} sd={3} />
        {ruedas}
      </g>
    );
  if (r === 'ochentas')
    return (
      <g>
        <Forma d="M-200 30 L-200 -30 L-110 -40 L-70 -100 L90 -100 L130 -40 L200 -30 L200 30 Z" fill={color} sd={16} brillo={[-120, -24, 60, 5]}>
          <rect x={-60} y={-92} width={70} height={46} fill={vidrio} stroke={C} strokeWidth={4} />
          <rect x={20} y={-92} width={90} height={46} fill={vidrio} stroke={C} strokeWidth={4} />
        </Forma>
        {ruedas}
      </g>
    );
  return (
    <g>
      <Forma d="M-180 30 L-180 -20 Q-170 -40 -120 -44 L-70 -100 L80 -100 L130 -44 Q175 -40 180 -10 L180 30 Z" fill={color} sd={16} brillo={[-120, -30, 50, 6]}>
        <path d="M-60 -90 L-20 -90 L-20 -46 L-100 -46 Z M0 -90 L70 -90 L110 -46 L0 -46 Z" fill={vidrio} stroke={C} strokeWidth={4} />
      </Forma>
      {ruedas}
    </g>
  );
};

const Farol: React.FC<{r: string}> = ({r}) => {
  if (r === 'antes')
    return (
      <g>
        <Forma d={dRect(-10, -520, 20, 520)} fill="#2b2b33" b={5} sd={4} />
        <Forma d={dRect(-30, -40, 60, 40, 6)} fill="#2b2b33" b={5} sd={5} />
        <circle cx={0} cy={-560} r={70} fill="#fff3b0" opacity={0.25} />
        <Forma d="M-40 -520 L40 -520 L28 -600 L-28 -600 Z" fill="#fff3b0" b={6} sd={6} />
        <Forma d="M-46 -600 L46 -600 L0 -640 Z" fill="#2b2b33" b={5} sd={4} />
      </g>
    );
  if (r === 'medio' || r === 'ochentas')
    return (
      <g>
        <Forma d={dRect(-10, -600, 20, 600)} fill={P.grisOscuro} b={5} sd={4} />
        <path d="M0 -600 Q0 -660 80 -660 L120 -660" fill="none" stroke={C} strokeWidth={22} strokeLinecap="round" />
        <path d="M0 -600 Q0 -660 80 -660 L120 -660" fill="none" stroke={P.grisOscuro} strokeWidth={12} strokeLinecap="round" />
        <circle cx={120} cy={-640} r={60} fill="#fff3b0" opacity={0.22} />
        <Forma d={dElipse(120, -650, 40, 14)} fill="#fff3b0" b={5} sd={4} />
      </g>
    );
  return (
    <g>
      <Forma d={dRect(-8, -620, 16, 620)} fill={P.gris} b={5} sd={4} />
      <Forma d={dRect(-8, -640, 120, 18, 6)} fill={P.gris} b={5} sd={4} />
      <rect x={60} y={-626} width={50} height={10} fill="#e6f7ff" />
    </g>
  );
};

const Ciudad: React.FC<FondoProps> = ({semilla, cam, t}) => {
  const [dec, variante] = epocaDe(semilla);
  const r = rango(dec);
  const ran = rnd(semilla);
  const filas = [
    {color: '#a9b8e8', base: H * 0.72, min: 380, max: 820, f: 0.45, ventanas: false},
    {color: '#6f7fc7', base: H * 0.8, min: 300, max: 700, f: 0.75, ventanas: true},
  ];
  const toldo = ({antes: '#8e2c2c', medio: '#2a9d8f', ochentas: '#ff99c8', hoy: '#3a86ff'} as Record<string, string>)[r];
  return (
    <g>
      <g transform={parallax(cam, 0.15)}>
        <rect x={-300} y={-300} width={W + 600} height={H + 600} fill="url(#atardecer)" />
        <circle cx={270} cy={520} r={170} fill="#ffe08a" opacity={0.35} />
        <circle cx={270} cy={520} r={130} fill="#ffe08a" />
        <g transform={`translate(${(t * 10) % 300} 0)`}>
          <Nube x={700} y={260} s={0.7} />
          <Nube x={180} y={180} s={0.5} />
        </g>
      </g>
      {filas.map((fl, k) => {
        const edif: React.ReactNode[] = [];
        let x = -140;
        let i = 0;
        while (x < W + 140) {
          const w = 140 + ran() * 90;
          const h = fl.min + ran() * (fl.max - fl.min);
          const top = fl.base - h;
          edif.push(
            <Forma key={i++} d={dRect(x, top, w, h + 40, 6)} fill={fl.color} b={k ? 6 : 4} sd={k ? 16 : 10} sinSombra={!k}>
              {fl.ventanas
                ? Array.from({length: Math.floor((h - 100) / 80)}, (_, a) =>
                    Array.from({length: Math.floor((w - 50) / 56)}, (_, b) => (
                      <rect key={`${a}_${b}`} x={x + 24 + b * 56} y={top + 40 + a * 80} width={30} height={42} rx={4} fill={ran() < 0.7 ? '#ffe58a' : '#4c5aa0'} stroke={C} strokeWidth={4} />
                    )),
                  )
                : Array.from({length: Math.floor((h - 60) / 90)}, (_, a) => <rect key={a} x={x + 20} y={top + 30 + a * 90} width={w - 40} height={10} fill={mezclar(fl.color, '#fff', 0.25)} />)}
            </Forma>,
          );
          x += w + (ran() * 28 - 10);
        }
        return (
          <g key={k} transform={parallax(cam, fl.f)}>
            {edif}
            {!k ? <rect x={-300} y={fl.base - 900} width={W + 600} height={900} fill="#ffd9a8" opacity={0.25} /> : null}
          </g>
        );
      })}
      {/* vereda y calle en perspectiva */}
      <rect x={-200} y={H * 0.8} width={W + 400} height={H * 0.2 + 200} fill="#5d6270" />
      <path d={`M-200 ${H * 0.8} H${W + 200} V${H * 0.8 + 70} H-200 Z`} fill="#9aa0ab" stroke={C} strokeWidth={5} />
      {Array.from({length: 12}, (_, i) => <path key={i} d={`M${i * 100 - 40} ${H * 0.8} l-10 70`} stroke={C} strokeWidth={3} opacity={0.35} />)}
      {Array.from({length: 6}, (_, i) => <path key={'c' + i} d={`M${40 + i * 220} ${H * 0.9} h120 l14 20 h-120 Z`} fill={P.blanco} opacity={0.9} />)}
      <rect x={-200} y={H * 0.8} width={W + 400} height={H * 0.2 + 200} fill="url(#pisoSombra)" />
      {/* vidriera de la época */}
      <Forma d={dRect(40, 1180, 380, 290, 6)} fill={r === 'antes' ? '#f5e6c8' : '#e9eef3'} sd={14} />
      <Forma d={dRect(70, 1240, 320, 200)} fill="#bfe9ff" b={5} sinSombra>
        <path d="M70 1300 L160 1240 H220 L70 1380 Z" fill="#fff" opacity={0.5} />
        <rect x={120} y={1360} width={60} height={80} fill={P.rojo} stroke={C} strokeWidth={4} />
        <rect x={220} y={1330} width={60} height={110} fill={P.amarillo} stroke={C} strokeWidth={4} />
      </Forma>
      {Array.from({length: 6}, (_, k) => (
        <path key={k} d={`M${40 + k * 64} 1150 L${104 + k * 64} 1150 L${98 + k * 64} 1200 L${46 + k * 64} 1200 Z`} fill={k % 2 === 0 ? toldo : P.blanco} stroke={C} strokeWidth={4} />
      ))}
      <path d="M40 1200 Q72 1218 104 1200 Q136 1218 168 1200 Q200 1218 232 1200 Q264 1218 296 1200 Q328 1218 360 1200 Q392 1218 424 1200" fill="none" stroke={C} strokeWidth={4} />
      <g transform="translate(980 1520)"><Farol r={r} /></g>
      <ellipse cx={640} cy={1556} rx={210} ry={22} fill="url(#contacto)" />
      <g transform="translate(640 1500) scale(0.9)"><Auto r={r} color={[P.rojo, P.azul, P.verde, P.amarillo][variante % 4]} /></g>
    </g>
  );
};

const Cielo: React.FC<FondoProps> = ({semilla, cam, t}) => {
  const ran = rnd(semilla);
  const nubes = Array.from({length: 5}, (_, i) => [80 + ran() * (W - 160), 180 + i * 230 + ran() * 80 - 40, 0.7 + ran() * 0.6] as [number, number, number]);
  const colina = (y: number, amp: number, s: number) => {
    const r2 = rnd(s);
    const pts = Array.from({length: 8}, (_, i) => [-300 + i * 240, y - r2() * amp] as [number, number]);
    let d = `M-300 ${H + 300} L${pts[0][0]} ${pts[0][1]} `;
    for (let i = 0; i < pts.length - 1; i++) d += `Q${(pts[i][0] + pts[i + 1][0]) / 2} ${Math.min(pts[i][1], pts[i + 1][1]) - amp * 0.6} ${pts[i + 1][0]} ${pts[i + 1][1]} `;
    return d + `L${W + 300} ${H + 300} Z`;
  };
  return (
    <g>
      <g transform={parallax(cam, 0.1)}>
        <rect x={-300} y={-300} width={W + 600} height={H + 600} fill="url(#cieloDeg)" />
        {Array.from({length: 12}, (_, i) => (
          <path key={i} d={`M840 300 L${840 + Math.cos((i * 30 + t * 8) * (Math.PI / 180)) * 260} ${300 + Math.sin((i * 30 + t * 8) * (Math.PI / 180)) * 260}`} stroke="#fff3b0" strokeWidth={26} opacity={0.25} strokeLinecap="round" />
        ))}
        <Forma d={dCirculo(840, 300, 110)} fill={P.amarillo} sd={14} brillo={[800, 260, 30, 20]} />
      </g>
      <g transform={parallax(cam, 0.3)}>
        {nubes.map(([x, y, s], i) => <Nube key={i} x={((x + t * (14 + i * 4)) % (W + 300)) - 150} y={y} s={s} />)}
      </g>
      <g transform={parallax(cam, 0.6)}>
        <Forma d={colina(H * 0.74, 120, semilla + 1)} fill="#9ad97f" sd={20} />
      </g>
      <g transform={parallax(cam, 0.85)}>
        <Forma d={colina(H * 0.84, 90, semilla + 2)} fill={P.verde} sd={22}>
          {Array.from({length: 30}, (_, i) => <path key={i} d={`M${(i * 97) % W} ${H * 0.86 + ((i * 53) % 200)} l6 -18 l6 18`} fill="none" stroke="#2f8a45" strokeWidth={4} />)}
        </Forma>
      </g>
    </g>
  );
};

const Escenario: React.FC<FondoProps> = ({t}) => (
  <g>
    <rect x={0} y={0} width={W} height={H} fill="#3b1f4a" />
    {Array.from({length: 12}, (_, i) => (
      <Forma key={i} d={`M${i * 90} 0 h90 v${H * 0.72} q-45 ${10 + Math.sin(t + i) * 4} -90 0 Z`} fill={i % 2 ? '#b3263a' : '#c9384b'} b={4} sd={20} />
    ))}
    <Forma d={`M0 0 L${W} 0 L${W} 120 Q${W * 0.75} 200 ${W / 2} 140 Q${W * 0.25} 200 0 120 Z`} fill="#8e1b2c" sd={16} />
    {[180, 900].map((x) => (
      <g key={x}>
        <path d={`M${x} 0 L${x - 260} ${H * 0.74} L${x + 260} ${H * 0.74} Z`} fill="#fff3b0" opacity={0.16 + Math.sin(t * 2 + x) * 0.03} />
        <Forma d={dCirculo(x, 40, 50)} fill={P.grisOscuro} sd={8} />
      </g>
    ))}
    <path d={`M-20 ${H * 0.72} H${W + 20} V${H + 20} H-20 Z`} fill="#a8714a" stroke={C} strokeWidth={6} />
    {Array.from({length: 9}, (_, i) => {
      const xb = (i * W) / 8;
      return <path key={i} d={`M${xb} ${H * 0.72} L${540 + (xb - 540) * 1.8} ${H}`} stroke="#8a5a38" strokeWidth={5} />;
    })}
    <rect x={0} y={H * 0.72} width={W} height={H * 0.28} fill="url(#pisoSombra)" />
  </g>
);

const FONDOS: Record<string, React.FC<FondoProps>> = {casa: Casa, taller: Taller, oficina: Oficina, fabrica: Fabrica, tienda: Tienda, ciudad: Ciudad, cielo: Cielo, escenario: Escenario};

export const DefsFondo: React.FC = () => (
  <defs>
    <linearGradient id="paredLuz" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stopColor="#fff" stopOpacity="0.12" />
      <stop offset="0.7" stopColor="#fff" stopOpacity="0" />
      <stop offset="1" stopColor="#2a1f4d" stopOpacity="0.12" />
    </linearGradient>
    <linearGradient id="pisoSombra" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stopColor="#2a1f4d" stopOpacity="0.35" />
      <stop offset="0.25" stopColor="#2a1f4d" stopOpacity="0.08" />
      <stop offset="1" stopColor="#2a1f4d" stopOpacity="0" />
    </linearGradient>
    <linearGradient id="cieloDeg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stopColor="#6cc4f5" />
      <stop offset="1" stopColor="#d6f1ff" />
    </linearGradient>
    <linearGradient id="atardecer" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stopColor="#ff9f7a" />
      <stop offset="0.5" stopColor="#ffc59a" />
      <stop offset="1" stopColor="#ffe2b8" />
    </linearGradient>
  </defs>
);

export const Fondo: React.FC<{f: [string, number | string]; cam: Cam; t: number; legacy?: string}> = ({f, cam, t, legacy}) => {
  const [tipo, s] = f;
  if (tipo === 'color') return <rect x={-W} y={-H} width={W * 3} height={H * 3} fill={String(s)} />;
  const F = FONDOS[tipo];
  if (!F) return legacy ? <g dangerouslySetInnerHTML={{__html: legacy}} /> : <rect width={W} height={H} fill="#888" />;
  const semilla = Number(s);
  const espejo = semilla >= 1000 && (semilla % 100) % 2 === 1;
  const camE: Cam = espejo ? [cam[0], -cam[1], cam[2], cam[3]] : cam;
  const el = <F semilla={semilla} cam={camE} t={t} />;
  return espejo ? <g transform={`translate(${W} 0) scale(-1 1)`}>{el}</g> : el;
};
