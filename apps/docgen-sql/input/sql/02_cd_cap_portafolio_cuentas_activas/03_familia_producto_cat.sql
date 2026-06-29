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
--\____________________________________________________________________________________________________________________________________/

INSERT OVERWRITE TABLE ${esquema_cu}.cu_cap_cat_familia_producto  
SELECT 
     cta.ID_CUENTA
    ,TRIM(fcproducto_subproducto) AS cod_producto
    ,CASE
        WHEN TRIM(fcnuevo_producto_nivel_03) = "Captacion" AND TRIM(fcnuevo_producto_nivel_04) IN ("Nomina") THEN "NOMINA" 
        WHEN TRIM(fcnuevo_producto_nivel_03) = "Captacion" AND TRIM(fcnuevo_producto_nivel_04) IN ("Inversion") THEN "INVERSION"
        WHEN TRIM(fcnuevo_producto_nivel_03) = "Captacion" AND TRIM(fcnuevo_producto_nivel_04) IN ("Ahorro") THEN "AHORRO"
        WHEN TRIM(fcnuevo_producto_nivel_03) = "Captacion" AND TRIM(fcnuevo_producto_nivel_04) IN ("Colaboradores") THEN "COLABORADOR"
        WHEN TRIM(fcnuevo_producto_nivel_03) = "BIG" AND TRIM(fcnuevo_producto_nivel_04) IN ("Programas Sociales") THEN 'PGS'
      ELSE "SECTOR CORPORATIVO"
     END AS cod_familia_producto
    ,TRIM(fcnivel) AS cod_nivel_cuenta
    ,TRIM(fcnuevo_producto_nivel_01) AS cod_producto_nivel_01	 
    ,TRIM(fcnuevo_producto_nivel_02) AS cod_producto_nivel_02	 
    ,TRIM(fcnuevo_producto_nivel_03) AS cod_producto_nivel_03	 
    ,TRIM(fcnuevo_producto_nivel_04) AS cod_producto_nivel_04           
    ,TRIM(fcnuevo_producto_nivel_05) AS cod_producto_nivel_05             
    ,TRIM(fcnuevo_producto_nivel_06) AS cod_producto_nivel_06                                  
    ,IF(CTA.cod_producto IN('PF-0022','PF-0002'), CONCAT_WS(' ',cat.fcnuevo_producto_nivel_07,cast(CTA.plazodeposito as string),'Dias') ,cat.fcnuevo_producto_nivel_07) AS cod_producto_nivel_07
    ,cod_sistema
    ,CURRENT_TIMESTAMP()                                                    AS FEC_CARGA
FROM ${esquema_cu}.cu_cap_universo_cuentas CTA
LEFT JOIN cu_gs_bdsopoperlog.cu_ebx_catm_gs_productos_captacion_niveles cat  on
    trim(cta.COD_PRODUCTO) = TRIM(cat.fcproducto_subproducto)
WHERE desc_cod_titular = "T-TITULAR"
;

COMPUTE STATS ${esquema_cu}.cu_cap_cat_familia_producto;