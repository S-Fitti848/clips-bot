// Los objetos con el estilo nuevo: mismas medidas y mismo origen que escenas.py (las cosas se apoyan y
// chocan donde el motor actual calculó), con volumen, brillos y más detalle. Lo que no está acá se dibuja
// con el SVG del motor actual (`legacy`), para que ningún guion se quede sin objeto.
import React from 'react';
import {C, P, Forma, Linea, dCirculo, dElipse, dRect, luz, sombra, mezclar} from './estilo';
import {Reloj} from './Tito';

const FUENTE = "'DejaVu Sans', 'Arial Black', sans-serif";

export const Texto: React.FC<{t: string; x?: number; y: number; tam: number; color: string; borde?: string; ab?: number}> = ({t, x = 0, y, tam, color, borde = C, ab}) => (
  <text x={x} y={y} fontFamily={FUENTE} fontWeight={900} fontSize={tam} textAnchor="middle" fill={color} stroke={borde} strokeWidth={ab ?? Math.max(4, tam * 0.16)} strokeLinejoin="round" paintOrder="stroke">
    {t}
  </text>
);

// semilla fija: los poros de la espuma no "bailan" entre cuadros
const poros = (() => {
  let s = 7;
  const r = () => ((s = (s * 16807) % 2147483647) / 2147483647);
  const out: [number, number, number, number][] = [];
  while (out.length < 30) {
    const x = r() * 124 - 62;
    const y = r() * 124 - 62;
    if (x * x + y * y < 58 * 58) out.push([x, y, 3 + r() * 6, 2.5 + r() * 4]);
  }
  return out;
})();

type PP = {color?: string; texto?: string; rota?: boolean; encendida?: boolean; forma?: number};

const Lamparita: React.FC<{color: string; encendida: boolean}> = ({color, encendida}) => (
  <g>
    {encendida
      ? [-70, -35, 0, 35, 70].map((a) => (
          <g key={a} transform={`translate(0 -20) rotate(${a})`}>
            <path d="M0 -150 L0 -205" stroke={C} strokeWidth={16} strokeLinecap="round" />
            <path d="M0 -150 L0 -205" stroke={P.amarillo} strokeWidth={8} strokeLinecap="round" />
          </g>
        ))
      : null}
    {encendida ? <circle cx={0} cy={-40} r={120} fill="#fff3b0" opacity={0.28} /> : null}
    <Forma d="M-80 -20 Q-80 -130 0 -130 Q80 -130 80 -20 Q80 30 40 60 L40 90 L-40 90 L-40 60 Q-80 30 -80 -20 Z" fill={encendida ? color : '#eef3f7'} sd={16} brillo={[-34, -84, 20, 30]}>
      <path d="M-20 60 L-20 10 Q0 -30 20 10 L20 60" fill="none" stroke={encendida ? '#e08a00' : P.gris} strokeWidth={6} />
    </Forma>
    <Forma d={dRect(-44, 90, 88, 50, 8)} fill={P.gris} sd={8}>
      <Linea d="M-44 106 L44 106 M-44 122 L44 122" w={6} o={0.5} />
    </Forma>
    <Forma d="M-16 140 L16 140 L8 156 L-8 156 Z" fill={P.grisOscuro} b={5} sd={3} />
  </g>
);

const P_NUEVOS: Record<string, React.FC<PP>> = {
  pelota_espuma: ({color = P.naranja}) => (
    <g>
      <Forma d={dCirculo(0, 0, 78)} fill={color} sd={20} brillo={[-30, -40, 24, 14]}>
        <rect x={-80} y={-17} width={160} height={34} fill={P.amarillo} />
        <rect x={-80} y={7} width={160} height={10} fill={sombra(P.amarillo)} />
        {poros.map(([x, y, rx, ry], i) => (
          <ellipse key={i} cx={x} cy={y} rx={rx} ry={ry} fill={mezclar(color, '#7a2a00', 0.35)} opacity={0.75} />
        ))}
      </Forma>
    </g>
  ),
  pelota: ({color = P.naranja}) => (
    <Forma d={dCirculo(0, 0, 70)} fill={color} sd={18} brillo={[-24, -30, 20, 12]}>
      {[[-30, -20], [10, -35], [25, 15], [-15, 25], [40, -5], [-40, 10]].map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r={8} fill={mezclar(color, '#7a2a00', 0.3)} />
      ))}
    </Forma>
  ),
  tele: ({rota}) => (
    <g>
      <path d="M-40 -120 L-80 -192 M40 -120 L80 -192" stroke={C} strokeWidth={7} strokeLinecap="round" />
      <circle cx={-80} cy={-194} r={8} fill={P.grisOscuro} stroke={C} strokeWidth={4} />
      <circle cx={80} cy={-194} r={8} fill={P.grisOscuro} stroke={C} strokeWidth={4} />
      <Forma d={dRect(-90, 104, 24, 26, 4)} fill={P.grisOscuro} b={5} sd={4} />
      <Forma d={dRect(66, 104, 24, 26, 4)} fill={P.grisOscuro} b={5} sd={4} />
      <Forma d={dRect(-150, -120, 300, 230, 22)} fill="#8d6e63" sd={20} brillo={[-110, -100, 30, 8]}>
        {/* veta de la madera */}
        <Linea d="M-150 -80 Q-60 -90 150 -78 M-150 60 Q0 50 150 66 M-150 96 Q20 90 150 100" w={4} o={0.18} />
      </Forma>
      <Forma d={dRect(-125, -98, 210, 180, 26)} fill={rota ? '#2f3842' : '#4f6070'} b={6} sd={10}>
        {!rota ? (
          <>
            <ellipse cx={-20} cy={-8} rx={110} ry={86} fill="#5f7385" />
            <path d="M-100 -76 L-60 -76 L-100 -36 Z" fill="#9fb4c6" opacity={0.85} />
            <Linea d="M-110 -40 L70 -40 M-110 0 L70 0 M-110 40 L70 40" w={2} o={0.12} color="#fff" />
          </>
        ) : (
          <path d="M-20 -20 L-110 -80 M-20 -20 L60 -90 M-20 -20 L-90 60 M-20 -20 L70 60 M-20 -20 L-60 -90 M-50 -40 L-80 -10 M20 -50 L40 -10" fill="none" stroke="#e3f6ff" strokeWidth={5} strokeLinecap="round" />
        )}
      </Forma>
      <Forma d={dCirculo(112, -50, 13)} fill={P.grisOscuro} b={5} sd={4} brillo={[108, -54, 4, 3]} />
      <Forma d={dCirculo(112, -10, 13)} fill={P.grisOscuro} b={5} sd={4} brillo={[108, -14, 4, 3]} />
      <Linea d="M98 30 L126 30 M98 42 L126 42 M98 54 L126 54" w={4} o={0.5} />
    </g>
  ),
  lampara: ({color = P.amarillo}) => (
    <g>
      <Forma d={dElipse(0, 165, 80, 22)} fill={P.grisOscuro} sd={8} brillo={[-30, 158, 18, 5]} />
      <Forma d={dRect(-12, -10, 24, 170, 6)} fill={P.grisOscuro} b={6} sd={6} brillo={[-5, 40, 3, 40]} />
      <circle cx={0} cy={-60} r={130} fill="#fff3b0" opacity={0.16} />
      <Forma d="M-70 -10 L70 -10 L110 -150 L-110 -150 Z" fill={color} sd={18} brillo={[-60, -120, 14, 20]}>
        <rect x={-120} y={-30} width={240} height={20} fill={sombra(color)} />
        <Linea d="M-40 -150 L-30 -10 M0 -150 L0 -10 M40 -150 L30 -10" w={3} o={0.2} />
      </Forma>
    </g>
  ),
  cuadro: ({color = P.verde}) => (
    <g>
      <path d="M-40 -110 L0 -150 L40 -110" fill="none" stroke={C} strokeWidth={5} />
      <circle cx={0} cy={-150} r={6} fill={P.grisOscuro} />
      <Forma d={dRect(-130, -110, 260, 200, 6)} fill={P.madera} sd={14} brillo={[-100, -100, 40, 5]}>
        <Linea d="M-118 -98 L118 -98 L118 78 L-118 78 Z" w={3} o={0.3} />
      </Forma>
      <Forma d={dRect(-108, -88, 216, 156)} fill="#bfe3ff" b={5} sinSombra>
        <rect x={-108} y={10} width={216} height={60} fill="#d9f0ff" />
        <path d="M-108 68 L-40 -10 L10 40 L50 0 L108 68 Z" fill={color} stroke={C} strokeWidth={4} />
        <path d="M-108 68 L-40 -10 L-20 14 L-60 68 Z" fill={luz(color)} opacity={0.5} />
        <circle cx={60} cy={-50} r={18} fill={P.amarillo} stroke={C} strokeWidth={4} />
      </Forma>
    </g>
  ),
  jarron: ({color = P.turquesa}) => (
    <Forma d="M-40 -120 L40 -120 L30 -90 Q100 -40 80 60 Q60 120 0 120 Q-60 120 -80 60 Q-100 -40 -30 -90 Z" fill={color} sd={20} brillo={[-40, -30, 12, 40]}>
      <path d="M-70 0 Q0 34 70 0" fill="none" stroke="#fff" strokeWidth={9} />
      <path d="M-74 30 Q0 64 74 30" fill="none" stroke={mezclar(color, '#000', 0.25)} strokeWidth={6} />
      {[-40, 0, 40].map((x) => <circle key={x} cx={x} cy={14 + Math.abs(x) * -0.1} r={7} fill="#fff" />)}
    </Forma>
  ),
  mesa: () => (
    <g>
      <Forma d={dRect(-130, 26, 22, 200, 3)} fill={sombra(P.madera)} b={6} sd={6} />
      <Forma d={dRect(108, 26, 22, 200, 3)} fill={sombra(P.madera)} b={6} sd={6} />
      <Forma d="M-150 0 L150 0 L150 30 L-150 30 Z" fill={P.madera} sd={10} brillo={[-80, 6, 60, 3]}>
        <Linea d="M-150 14 Q0 8 150 16" w={3} o={0.2} />
      </Forma>
    </g>
  ),
  estante: () => (
    <g>
      <Forma d="M-110 24 L-110 70 L-70 24 Z" fill={sombra(P.madera)} b={5} sd={4} />
      <Forma d="M110 24 L110 70 L70 24 Z" fill={sombra(P.madera)} b={5} sd={4} />
      <Forma d={dRect(-140, 0, 280, 24, 4)} fill={P.madera} sd={8} brillo={[-60, 5, 60, 3]} />
    </g>
  ),
  ventana: ({rota}) => (
    <g>
      <Forma d={dRect(-188, -218, 376, 436, 8)} fill={P.crema} sd={12} />
      <Forma d={dRect(-170, -200, 340, 400, 6)} fill={P.vidrio} b={6} sinSombra>
        <rect x={-170} y={40} width={340} height={160} fill="#c9f0ff" />
        <ellipse cx={-60} cy={-110} rx={70} ry={26} fill="#fff" opacity={0.9} />
        {!rota ? <path d="M-140 -170 L-90 -170 L-140 -120 Z M60 20 L120 20 L60 80 Z" fill="#fff" opacity={0.8} /> : null}
      </Forma>
      <path d="M0 -200 L0 200 M-170 0 L170 0" stroke={C} strokeWidth={18} />
      <path d="M0 -200 L0 200 M-170 0 L170 0" stroke={P.crema} strokeWidth={9} />
      {rota ? (
        <g>
          <Forma d={dCirculo(60, -70, 36)} fill="#e3f6ff" b={4} sinSombra />
          {Array.from({length: 9}, (_, i) => {
            const a = (i * 40 * Math.PI) / 180;
            return <path key={i} d={`M60 -70 L${60 + 150 * Math.cos(a)} ${-70 + 150 * Math.sin(a)}`} stroke={C} strokeWidth={5} strokeLinecap="round" />;
          })}
        </g>
      ) : null}
      <Forma d={dRect(-200, 214, 400, 20, 4)} fill={P.crema} b={5} sd={5} />
    </g>
  ),
  pedazo: ({color = '#9fe3ff', forma = 0}) => {
    const fs = ['M-30 -20 L30 -26 L6 30 Z', 'M-24 -30 L26 -6 L-12 28 Z', 'M-28 10 L0 -32 L30 20 Z', 'M-20 -24 L32 0 L-6 22 L-26 6 Z'];
    return <Forma d={fs[Math.abs(Math.round(forma)) % fs.length]} fill={color} b={5} sd={6} />;
  },
  lamparita: ({color = P.amarillo, encendida = true}) => <Lamparita color={color} encendida={encendida !== false} />,
  idea_fallida: () => (
    <g>
      <Lamparita color={P.amarillo} encendida={false} />
      <path d="M-30 -110 L-6 -70 L-30 -40 L4 -6" fill="none" stroke={C} strokeWidth={7} strokeLinejoin="round" />
    </g>
  ),
  pregunta: ({color = P.amarillo}) => <Texto t="?" y={90} tam={260} color={color} ab={24} />,
  exclamacion: ({color = P.rojo}) => <Texto t="!" y={90} tam={260} color={color} ab={24} />,
  moneda: ({color = P.amarillo}) => (
    <g>
      <Forma d={dCirculo(0, 0, 110)} fill="#e8a920" sd={18} brillo={[-50, -60, 20, 12]} />
      <Forma d={dCirculo(0, 0, 84)} fill={color} b={5} sd={10} />
      {Array.from({length: 24}, (_, i) => {
        const a = (i * 15 * Math.PI) / 180;
        return <path key={i} d={`M${Math.cos(a) * 92} ${Math.sin(a) * 92} L${Math.cos(a) * 104} ${Math.sin(a) * 104}`} stroke="#b07d1c" strokeWidth={4} />;
      })}
      <Texto t="$" y={44} tam={120} color="#e8a920" ab={10} />
    </g>
  ),
  billete: ({color = P.verde, texto = '$'}) => (
    <g>
      <Forma d={dRect(-170, -85, 340, 170, 12)} fill={color} sd={12} brillo={[-120, -70, 40, 6]} />
      <Forma d={dRect(-140, -60, 280, 120, 8)} fill="#a8e6a1" b={5} sd={6}>
        <Linea d="M-130 -40 Q-60 -60 0 -40 Q60 -20 130 -40 M-130 40 Q-60 20 0 40 Q60 60 130 40" w={3} o={0.3} />
      </Forma>
      <Forma d={dCirculo(0, 0, 46)} fill={color} b={5} sd={6} />
      <Texto t={texto && texto.length <= 3 ? texto : '$'} y={22} tam={64} color={P.blanco} ab={8} />
    </g>
  ),
  martillo: () => (
    <g>
      <Forma d={dRect(-12, -40, 24, 200, 8)} fill={P.madera} b={6} sd={6} brillo={[-4, 40, 3, 60]}>
        <rect x={-14} y={110} width={28} height={50} fill={P.rojo} />
      </Forma>
      <Forma d="M-70 -90 L70 -90 L74 -60 L70 -30 L-70 -30 Q-86 -60 -70 -90 Z" fill={P.grisOscuro} sd={10} brillo={[-30, -80, 40, 5]} />
    </g>
  ),
  caja: ({color = P.amarillo, texto = ''}) => (
    <g>
      <Forma d="M-110 -150 L110 -150 L140 -180 L-80 -180 Z" fill={luz(color)} b={6} sd={4} />
      <Forma d="M110 -150 L140 -180 L140 140 L110 170 Z" fill={sombra(color)} b={6} sd={6} />
      <Forma d={dRect(-110, -150, 220, 320)} fill={color} sd={14} brillo={[-80, -110, 10, 50]}>
        <circle cx={-40} cy={80} r={34} fill={P.madera} stroke={C} strokeWidth={4} />
        <circle cx={40} cy={80} r={34} fill={P.madera} stroke={C} strokeWidth={4} />
        <circle cx={-50} cy={70} r={6} fill="#5a3a1a" />
        <circle cx={30} cy={88} r={6} fill="#5a3a1a" />
      </Forma>
      <Forma d={dRect(-80, -110, 160, 90, 10)} fill={P.blanco} b={5} sd={6} />
      {texto ? <Texto t={texto.slice(0, 14)} y={-50} tam={Math.max(18, Math.min(40, Math.floor(240 / Math.max(1, texto.length))))} color={C} borde={P.blanco} ab={5} /> : null}
    </g>
  ),
  reloj_bolsillo: () => <Reloj aguja={40} r={90} />,
  engranaje: ({color = P.gris}) => (
    <g>
      {Array.from({length: 8}, (_, i) => (
        <g key={i} transform={`rotate(${i * 45})`}>
          <Forma d={dRect(-22, -122, 44, 54, 6)} fill={color} b={6} sd={6} />
        </g>
      ))}
      <Forma d={dCirculo(0, 0, 90)} fill={color} sd={16} brillo={[-34, -40, 18, 10]}>
        <circle cx={0} cy={0} r={62} fill="none" stroke={C} strokeWidth={4} opacity={0.3} />
      </Forma>
      <Forma d={dCirculo(0, 0, 30)} fill={P.blanco} b={6} sd={6} />
    </g>
  ),
  trofeo: ({color = P.amarillo}) => (
    <g>
      <path d="M-100 -120 Q-170 -120 -160 -60 Q-150 -10 -80 -10 M100 -120 Q170 -120 160 -60 Q150 -10 80 -10" fill="none" stroke={C} strokeWidth={22} strokeLinecap="round" />
      <path d="M-100 -120 Q-170 -120 -160 -60 Q-150 -10 -80 -10 M100 -120 Q170 -120 160 -60 Q150 -10 80 -10" fill="none" stroke={color} strokeWidth={10} strokeLinecap="round" />
      <Forma d={dRect(-80, 100, 160, 50, 8)} fill={P.madera} sd={8} />
      <Forma d={dRect(-22, 36, 44, 70)} fill={sombra(color)} b={6} sd={6} />
      <Forma d="M-100 -150 L100 -150 Q100 0 0 40 Q-100 0 -100 -150 Z" fill={color} sd={18} brillo={[-50, -110, 12, 40]}>
        <path d="M0 -110 l10 22 24 2 -18 16 6 24 -22 -12 -22 12 6 -24 -18 -16 24 -2 Z" fill={luz(color)} stroke={C} strokeWidth={3} />
      </Forma>
    </g>
  ),
  grafico_sube: ({color = P.verde}) => {
    const pts = [[-150, 80], [-80, 30], [-20, 60], [50, -20], [130, -110]];
    const d = 'M' + pts.map(([x, y]) => `${x} ${y}`).join(' L');
    return (
      <g>
        <Forma d={dRect(-190, -170, 380, 320, 14)} fill={P.blanco} sd={12} />
        <Linea d="M-160 70 L170 70 M-160 10 L170 10 M-160 -50 L170 -50 M-160 -110 L170 -110" w={2} o={0.15} />
        <path d="M-160 130 L170 130 M-160 130 L-160 -150" stroke={C} strokeWidth={5} />
        <path d={d} fill="none" stroke={C} strokeWidth={30} strokeLinejoin="round" strokeLinecap="round" />
        <path d={d} fill="none" stroke={color} strokeWidth={16} strokeLinejoin="round" strokeLinecap="round" />
        <Forma d="M96 -106 L146 -126 L126 -76 Z" fill={color} b={5} sd={4} />
      </g>
    );
  },
  bolsa_plata: ({color = '#d6a45a'}) => (
    <g>
      <Forma d="M-40 -120 Q-60 -150 -30 -160 L30 -160 Q60 -150 40 -120 Q150 -40 140 80 Q130 160 0 160 Q-130 160 -140 80 Q-150 -40 -40 -120 Z" fill={color} sd={22} brillo={[-60, -20, 20, 50]}>
        <Linea d="M-60 -90 Q-90 0 -70 100 M40 -100 Q80 -20 70 60" w={4} o={0.25} />
      </Forma>
      <path d="M-50 -118 L50 -118" stroke={C} strokeWidth={14} strokeLinecap="round" />
      <path d="M-50 -118 L50 -118" stroke="#8a5a2b" strokeWidth={6} strokeLinecap="round" />
      <Texto t="$" y={70} tam={150} color={P.verde} ab={12} />
    </g>
  ),
  cartel: ({color = P.amarillo, texto = '¡OJO!'}) => (
    <g>
      <Forma d={dRect(-14, 0, 28, 230, 4)} fill={P.madera} b={6} sd={6} />
      <Forma d={dRect(-190, -140, 380, 170, 14)} fill={color} sd={14} brillo={[-140, -124, 40, 6]} />
      <Texto t={texto} y={-36} tam={texto.length <= 8 ? 64 : 48} color={C} borde={P.blanco} ab={6} />
    </g>
  ),
  botella: ({color = P.rojo, texto = ''}) => (
    <g>
      <Forma d={dRect(-30, -262, 60, 36, 6)} fill={P.grisOscuro} b={6} sd={5} />
      <Forma d="M-26 -230 L26 -230 L26 -170 Q80 -130 80 -60 L80 200 Q80 230 50 230 L-50 230 Q-80 230 -80 200 L-80 -60 Q-80 -130 -26 -170 Z" fill={color} sd={18} brillo={[-50, -40, 9, 70]}>
        <rect x={-80} y={-10} width={160} height={110} fill={P.blanco} />
        <rect x={40} y={-10} width={40} height={110} fill={sombra(P.blanco)} />
      </Forma>
      {texto ? <Texto t={texto.slice(0, 12)} y={58} tam={Math.max(18, Math.min(40, Math.floor(240 / Math.max(1, texto.length))))} color={C} borde={P.blanco} ab={5} /> : null}
    </g>
  ),
  flecha: ({color = P.rojo}) => <Forma d="M-150 -36 L40 -36 L40 -90 L160 0 L40 90 L40 36 L-150 36 Z" fill={color} sd={14} brillo={[-80, -24, 60, 5]} />,
  calendario: ({color = P.rojo, texto = ''}) => (
    <g>
      <Forma d={dRect(-130, -130, 260, 260, 16)} fill={P.blanco} sd={14}>
        <rect x={-130} y={-130} width={260} height={70} fill={color} />
        <Linea d="M-110 -30 L110 -30 M-110 20 L110 20 M-110 70 L110 70 M-60 -50 L-60 110 M0 -50 L0 110 M60 -50 L60 110" w={2} o={0.12} />
      </Forma>
      {[-70, 70].map((x) => <Forma key={x} d={dCirculo(x, -130, 14)} fill={P.gris} b={5} sd={4} />)}
      <Texto t={texto.slice(0, 8)} y={60} tam={Math.max(34, Math.min(96, Math.floor(400 / Math.max(1, texto.slice(0, 8).length))))} color={C} borde={P.blanco} ab={6} />
    </g>
  ),
};

export const Prop: React.FC<{n: string; p: Record<string, unknown>; legacy?: string}> = ({n, p, legacy}) => {
  const F = P_NUEVOS[n];
  if (F) return <F {...(p as PP)} />;
  if (legacy) return <g dangerouslySetInnerHTML={{__html: legacy}} />;
  return null;
};
