import { Tarjeta } from "@/componentes/comunes";
import { BarrasRanking } from "@/componentes/graficos";
import { Indicador } from "@/componentes/indicadores";
import { fecha, numero } from "@/utilidades/formato";

const CORTE = "2026-11-17";
const PUNTOS = [
  { nombre: "PDV Pereira Dosquebradas", dias: 16 },
  { nombre: "PDV Bucaramanga", dias: 14 },
  { nombre: "PDV Cartagena", dias: 13 },
  { nombre: "PDV Centro", dias: 13 },
  { nombre: "PDV La 43", dias: 13 },
  { nombre: "PDV La 70", dias: 13 },
  { nombre: "PDV La 93", dias: 13 },
  { nombre: "PDV La Granja", dias: 13 },
  { nombre: "PDV Malambo", dias: 12 },
  { nombre: "PDV Simón", dias: 11 },
].map((punto) => ({
  ...punto,
  pendiente: 17 - punto.dias,
  fechaAcumulada: `2026-11-${punto.dias}`,
}));

const ABIERTOS = [
  { punto: "PDV Bucaramanga", codigo: "TPV412001" },
  { punto: "PDV Bucaramanga", codigo: "TPV412004" },
  { punto: "PDV Bucaramanga", codigo: "TPV412006" },
  { punto: "PDV Cartagena", codigo: "TPV415001" },
  { punto: "PDV Cartagena", codigo: "TPV415002" },
];

export function AcumulacionTpvDemo() {
  const [mayor] = PUNTOS;
  const menor = PUNTOS[PUNTOS.length - 1];
  const ranking = (campo: "dias" | "pendiente") => [...PUNTOS]
    .sort((primero, segundo) => segundo[campo] - primero[campo])
    .map((punto) => ({ clave: punto.nombre, etiqueta: punto.nombre, valor: String(punto[campo]) }));

  return (
    <>
      <Tarjeta titulo="Acumulación y cierre de TPV" descripcion={`Datos de ejemplo · Corte: ${fecha(CORTE)}`}>
        <div className="rejilla rejilla--grupos">
          {mayor ? <Indicador etiqueta="Mayor acumulación" valor={`${mayor.dias} días`} nota={mayor.nombre} /> : null}
          {menor ? <Indicador etiqueta="Menor acumulación" valor={`${menor.dias} días`} nota={menor.nombre} /> : null}
          <Indicador etiqueta="TPV sin cerrar" valor={numero(ABIERTOS.length)} />
        </div>
      </Tarjeta>

      <div className="rejilla rejilla--grupos">
        <Tarjeta titulo="Días sin acumulación por PDV">
          <BarrasRanking filas={ranking("pendiente")} formatear={numero} titulo="Días sin acumulación por PDV" />
        </Tarjeta>
        <Tarjeta titulo="Días acumulados por PDV">
          <BarrasRanking filas={ranking("dias")} formatear={numero} titulo="Días acumulados por PDV" />
        </Tarjeta>
      </div>

      <Tarjeta titulo="Detalle de acumulación por punto de venta" sinRelleno>
        <div className="tabla-envoltorio">
          <table className="tabla">
            <thead><tr>
              <th scope="col">Punto de venta</th>
              <th scope="col">Fecha acumulada</th>
              <th scope="col" className="numero">Días acumulados</th>
              <th scope="col" className="numero">Días sin acumulación</th>
            </tr></thead>
            <tbody>{PUNTOS.map((punto) => (
              <tr key={punto.nombre}>
                <th scope="row">{punto.nombre}</th>
                <td>{fecha(punto.fechaAcumulada)}</td>
                <td className="numero">{numero(punto.dias)}</td>
                <td className="numero">{numero(punto.pendiente)}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </Tarjeta>

      <Tarjeta titulo="TPV sin cerrar" sinRelleno>
        <div className="tabla-envoltorio">
          <table className="tabla">
            <thead><tr>
              <th scope="col">Punto de venta</th>
              <th scope="col">TPV</th>
              <th scope="col">Estado</th>
              <th scope="col">Fecha</th>
            </tr></thead>
            <tbody>{ABIERTOS.map((tpv) => (
              <tr key={tpv.codigo}>
                <td>{tpv.punto}</td>
                <th scope="row">{tpv.codigo}</th>
                <td>Abierto</td>
                <td>{fecha(CORTE)}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </Tarjeta>
    </>
  );
}