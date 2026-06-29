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
--|     # ${esquema_cu} = ws_ec_cu_baz_bdclientes
--|     # ${fec_ini_sem} = 2026-04-27
--\____________________________________________________________________________________________________________________________________/

--DROP TABLE  ${esquema_cu}.cu_finacle_saldos_decrypt;
--CREATE TABLE ${esquema_cu}.cu_finacle_saldos_decrypt STORED AS PARQUET AS 
insert overwrite table ${esquema_cu}.cu_finacle_saldos_decrypt
SELECT 
	id_cliente
	,id_cuenta
	,cta_encrypt
	,fechaapertura
	,fechacancelacion
	,centrocontable
	,fechaultimomovimiento
	,personalidad
	,estatuscuenta
	,moneda
	,saldototal
	,saldodisponible
	,producto
    ,plazodeposito
FROM
(
	select distinct
	     bdf_voltage_simpleapi_v2(identificadorcliente ,'rd_baz_bdclientes.rd_fin_maestrosaldos' ,'identificadorcliente' ,1 ,'error_bdf_voltage') as id_cliente
	    ,bdf_voltage_simpleapi_v2(cuenta ,'rd_baz_bdclientes.rd_fin_maestrosaldos' ,'cuenta' ,1 ,'error_bdf_voltage') as id_cuenta
	    ,cuenta as cta_encrypt
	    ,fechaapertura 
	    ,fechacancelacion
	    ,centrocontable  
	    ,fechaultimomovimiento 
	    ,personalidad 
	    ,estatuscuenta 
	    ,moneda 
	    ,bdf_voltage_simpleapi_v2(saldototal ,'rd_baz_bdclientes.rd_fin_maestrosaldos' ,'saldototal' ,1 ,'error_bdf_voltage') as saldototal
	    ,bdf_voltage_simpleapi_v2(saldodisponible ,'rd_baz_bdclientes.rd_fin_maestrosaldos' ,'saldodisponible' ,1 ,'error_bdf_voltage') as saldodisponible
	    ,producto
        ,plazodeposito
	from rd_baz_bdclientes.rd_fin_maestrosaldos sld
	where to_date(from_unixtime(unix_timestamp(trim(cast(fifecha as string)), 'yyyyMMdd'))) = '${fec_ini_sem}'
) AS a 
WHERE LOWER(id_cuenta) NOT LIKE '%x%';



