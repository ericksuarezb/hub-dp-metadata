-- ___________________________________________________________________________________________________________________________________
--/     #####   PROYECTO CRYSTAL DATA   #####
--| @FECHA DE CREACION:
--|     # Martes, 24 de Febrero del 2026
--| @DOMINIOS:                          
--|     # Captacion
--| @ARCHIVO:                           
--|     # 01_cd_cap_cuenta_delta.sql 
--| @AUTOR:                                     
--|     # Erick Suarez Buendia <erick.suarez@algorithia.com>
--|	# Brenda Sarahi Rosas Morán <brenda.rosasm@algorithia.com>
--| @DESCRIPCION:                        
--|     # 
--| @TIEMPOS DE EJECUCION:      
--|     # 
--| @MODIFICACIONES:
--|             # @FECHA                
--|             # @DESCRIPCION
--|     # 
--| @PARAMETROS
--|     # ${dia_fec_ini_sem} = 2026-05-03
--|     # ${esquema_cu} = ws_ec_cu_baz_bdclientes
--|     # ${num_periodo_mes} = 202604
--\____________________________________________________________________________________________________________________________________/


drop TABLE ${esquema_cu}.cu_cap_saldos_disponibles_ctas_prev;
create TABLE ${esquema_cu}.cu_cap_saldos_disponibles_ctas_prev stored as parquet as 
with 
_saldos_alnova_actual_ as (
select 
     concat(t503_cen_reg ,t503_acc) as id_cuenta
    ,t503_wdrwbal_${dia_fec_ini_sem} AS sld_disponible	
    ,'ALNOVA' cod_sistema
from rd_baz_bdclientes.rd_bgdt503
where t503_periodo = '${num_periodo_mes}'
),
_saldos_alnova_hist_ as (
select 
     concat(t504_cen_reg ,t504_acc) as id_cuenta		
    ,t504_wdrwbal_${dia_fec_ini_sem} AS sld_disponible		
    ,'ALNOVA' cod_sistema
from rd_baz_bdclientes.rd_bgdt504 --| # Para reprocesar historia
where t504_periodo = '${num_periodo_mes}'
)  
select 
     id_cuenta
    ,cast(sld.sld_disponible as decimal(32,2)) as  sld_disponible
    ,cod_sistema
    ,now() as fec_carga
from(
    select * from _saldos_alnova_actual_ as actual
    union all
    select * from _saldos_alnova_hist_ as hist
) sld
;

COMPUTE STATS ${esquema_cu}.cu_cap_saldos_disponibles_ctas_prev;

drop TABLE if exists ${esquema_cu}.cu_cap_saldos_disponibles_ctas;
create TABLE ${esquema_cu}.cu_cap_saldos_disponibles_ctas stored as parquet as
    
SELECT 
    DISTINCT 
     CTA.id_cuenta
    ,sld.sld_disponible
    ,CASE 
		when sld.sld_disponible <= 0      then  "(00) Sin saldo"
		when sld.sld_disponible <= 1      then  "(01) menor a 1"
		when sld.sld_disponible <= 50     then  "(02) 1 a 50"     
		when sld.sld_disponible <= 100    then  "(03) 50 - 100" 
		when sld.sld_disponible <= 1000   then  "(04) 100 - 1k" 
		when sld.sld_disponible <= 2500   then  "(05) 1k - 2.5k"
		when sld.sld_disponible <= 5000   then  "(06) 2.5k - 5k"
		when sld.sld_disponible <= 10000  then  "(07) 5k - 10k"
		when sld.sld_disponible <= 15000  then  "(08) 10k - 15k"
		when sld.sld_disponible <= 20000  then  "(09) 15k - 20k"
		when sld.sld_disponible <= 25000  then  "(10) 20k - 25k"
		when sld.sld_disponible <= 50000  then  "(11) 25k - 50k"
		when sld.sld_disponible <= 100000  then  "(12) 50k - 100k"
		when sld.sld_disponible <= 150000  then  "(13) 100k - 150k"
		when sld.sld_disponible <= 200000  then  "(14) 150k - 200k"	
		when sld.sld_disponible <= 250000  then  "(15) 200k - 250k"
		when sld.sld_disponible <= 300000  then  "(16) 250k - 300k"
		when sld.sld_disponible <= 350000  then  "(17) 300k - 350k"
		when sld.sld_disponible <= 400000  then  "(18) 350k - 400k"
		when sld.sld_disponible <= 450000  then  "(19) 400k - 450k"
		when sld.sld_disponible <= 500000  then  "(20) 450k - 500k"
		when sld.sld_disponible >  500000   then  "(21) + 500k"
	 	else "(00) Sin saldo" 
	END AS cod_sld_disponible
    ,cod_sistema
    ,CURRENT_TIMESTAMP()                                                    AS FEC_CARGA
FROM ${esquema_cu}.cu_cap_universo_cuentas CTA
LEFT JOIN(
    SELECT 
	 id_cuenta
     ,sld_disponible
	FROM (
	    select 
	         id_cuenta
	        ,ABS(sld_disponible) as sld_disponible
	        ,cod_sistema
	        ,ROW_NUMBER() OVER(PARTITION BY id_cuenta ORDER BY ABS(sld_disponible) DESC,cod_sistema DESC) AS rowid 
	    from(
	        select id_cuenta ,sld_disponible ,cod_sistema from ${esquema_cu}.cu_cap_saldos_disponibles_ctas_prev
	        union all
	        select id_cuenta ,cast(saldodisponible as decimal(32,2)) as sld_disponible ,'FINACLE' cod_sistema
	        from ${esquema_cu}.cu_finacle_saldos_decrypt
	        ) slds_totales
	    ) as slds_unico
	WHERE rowid=1
    ) sld on
trim(cta.id_cuenta) = TRIM(sld.id_cuenta)
;

COMPUTE STATS ${esquema_cu}.cu_cap_saldos_disponibles_ctas;