import { useQuery } from "@tanstack/react-query";
import { MODO_EJEMPLOS, peticion } from "@/api/cliente";
import { AvisoError, Cargando, Tarjeta, Vacio } from "@/componentes/comunes";
import { BarraFiltros, useFiltros } from "@/componentes/filtros";
import { BarrasRanking } from "@/componentes/graficos";
import { Indicador } from "@/componentes/indicadores";
import { fecha, numero } from "@/utilidades/formato";

const CORTE = "2026-11-17";
interface RespuestaTpv {
  fecha_corte: string;
  puntos: {
    codigo_co: string;
    nombre: string;
    fecha_acumulada: string | null;
    dias_acumulados: number;
    dias_sin_acumulacion: number;
    dias_sin_registros: number;
  }[];
  abiertas: {
    codigo_co: string;
    punto_venta: string;
    compania: number;
    tpv: string;
    fecha: string;
  }[];
}

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
].map((punto, indice) => ({
  codigo_co: String(indice),
  nombre: punto.nombre,
  dias_acumulados: punto.dias,
  dias_sin_acumulacion: 17 - punto.dias,
  dias_sin_registros: 0,
  fecha_acumulada: `2026-11-${punto.dias}`,
}));

const ABIERTOS = [
  { punto: "PDV Bucaramanga", codigo: "TPV412001" },
  { punto: "PDV Bucaramanga", codigo: "TPV412004" },
  { punto: "PDV Bucaramanga", codigo: "TPV412006" },
  { punto: "PDV Cartagena", codigo: "TPV415001" },
  { punto: "PDV Cartagena", codigo: "TPV415002" },
].map((caja) => ({
  codigo_co: caja.codigo.slice(3, 6),
  punto_venta: caja.punto,
  compania: 4,
  tpv: caja.codigo,
  fecha: CORTE,
}));

export function AcumulacionTpv() {
  const control = useFiltros();
  const { periodo, hasta, punto_venta } = control.filtros;
  const consulta = useQuery({
    queryKey: ["costos-tpv", periodo, hasta, punto_venta],
    queryFn: () => peticion<RespuestaTpv>("/reportes/costos/tpv", {
      parametros: { periodo, hasta, punto_venta },
    }),
    enabled: !MODO_EJEMPLOS,
    staleTime: 60_000,
  });
  const datos = MODO_EJEMPLOS ? { fecha_corte: CORTE, puntos: PUNTOS, abiertas: ABIERTOS } : consulta.data;

  return (
    <div className="pila">
      {!MODO_EJEMPLOS ? <BarraFiltros control={control} mostrar={{ grupo: false, categoria: false, medida: false }} /> : null}
      <AvisoError error={consulta.error} />
      {consulta.isLoading ? <Cargando texto="Consultando cierres de TPV…" /> : null}
      {datos ? <InformeTpv datos={datos} /> : null}
    </div>
  );
}

function InformeTpv({ datos }: { datos: RespuestaTpv }) {
  const { puntos, abiertas, fecha_corte } = datos;
  const [mayor] = puntos;
  const menor = puntos[puntos.length - 1];
  const ranking = (campo: "dias_acumulados" | "dias_sin_acumulacion") => [...puntos]
    .sort((primero, segundo) => segundo[campo] - primero[campo])
    .map((punto) => ({ clave: punto.codigo_co, etiqueta: punto.nombre, valor: String(punto[campo]) }));

  if (!puntos.length) return <Vacio titulo="Sin registros de TPV" detalle="No hay registros para los puntos de venta y el corte seleccionados." />;

  return (
    <>
      <Tarjeta
        titulo="Acumulación y cierre de TPV"
        descripcion={`${MODO_EJEMPLOS ? "Datos de ejemplo · " : ""}Corte: ${fecha(fecha_corte)}`}
        pie="Los días acumulados son los que no aparecen como pendientes en el reporte de TPV no acumuladas."
      >
        <div className="rejilla rejilla--grupos">
          {mayor ? <Indicador etiqueta="Mayor acumulación" valor={`${mayor.dias_acumulados} días`} nota={mayor.nombre} /> : null}
          {menor ? <Indicador etiqueta="Menor acumulación" valor={`${menor.dias_acumulados} días`} nota={menor.nombre} /> : null}
          <Indicador etiqueta="TPV sin cerrar" valor={numero(abiertas.length)} />
        </div>
      </Tarjeta>

      <div className="rejilla rejilla--grupos">
        <Tarjeta titulo="Días pendientes de acumulación por PDV">
          <BarrasRanking filas={ranking("dias_sin_acumulacion")} formatear={numero} titulo="Días pendientes de acumulación por PDV" />
        </Tarjeta>
        <Tarjeta titulo="Días acumulados por PDV">
          <BarrasRanking filas={ranking("dias_acumulados")} formatear={numero} titulo="Días acumulados por PDV" />
        </Tarjeta>
      </div>

      <Tarjeta titulo="Detalle de acumulación por punto de venta" sinRelleno>
        <div className="tabla-envoltorio">
          <table className="tabla">
            <thead><tr>
              <th scope="col">Punto de venta</th>
              <th scope="col">Fecha acumulada</th>
              <th scope="col" className="numero">Días acumulados</th>
              <th scope="col" className="numero">Días pendientes de acumulación</th>
              <th scope="col" className="numero">Días sin registros</th>
            </tr></thead>
            <tbody>{puntos.map((punto) => (
              <tr key={punto.codigo_co}>
                <th scope="row">{punto.nombre}</th>
                <td>{fecha(punto.fecha_acumulada)}</td>
                <td className="numero">{numero(punto.dias_acumulados)}</td>
                <td className="numero">{numero(punto.dias_sin_acumulacion)}</td>
                <td className="numero">{numero(punto.dias_sin_registros)}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </Tarjeta>

      <Tarjeta titulo="TPV sin cerrar" sinRelleno>
        {abiertas.length === 0 ? <Vacio titulo="No hay TPV abiertas para este corte" /> : <div className="tabla-envoltorio">
          <table className="tabla">
            <thead><tr>
              <th scope="col">Punto de venta</th>
              <th scope="col">TPV</th>
              <th scope="col">Estado</th>
              <th scope="col">Fecha</th>
            </tr></thead>
            <tbody>{abiertas.map((tpv) => (
              <tr key={`${tpv.compania}-${tpv.codigo_co}-${tpv.tpv}-${tpv.fecha}`}>
                <td>{tpv.punto_venta}</td>
                <th scope="row">{tpv.tpv}</th>
                <td>Abierto</td>
                <td>{fecha(tpv.fecha)}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>}
      </Tarjeta>
    </>
  );
}