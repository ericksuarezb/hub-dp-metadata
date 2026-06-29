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
--|     # ${esquema_cd} = wc_ec_cd_baz_bdclientes
--|     # ${esquema_cu} = ws_ec_cu_baz_bdclientes
--\____________________________________________________________________________________________________________________________________/


INSERT OVERWRITE TABLE ${esquema_cd}.cd_cap_portafolio_cuentas_activas
PARTITION(cod_titular)
SELECT 
    DISTINCT 
     id_cliente_alnova    
    ,id_cliente_finacle   
    ,id_cliente_unico     
    ,id_icu_digital       
    ,cod_tipo_persona     
    ,id_cuenta            
    ,id_sucursal_apertura 
    ,id_sucursal_gestora  
    ,desc_cod_titular     
    ,cod_estatus          
    ,fec_apertura  
    ,cod_bloqueo          
    ,cod_tipo_moneda      
    ,fec_ultima_txn       
    ,id_sucursal_ultima_txn
    ,cod_usuario_ultima_txn
    ,num_ultima_txn       
    ,num_dias_inactividad 
    ,ind_cuenta_nueva     
    ,num_dias_antiguedad  
    ,cod_producto         
    ,cod_familia_producto 
    ,cod_nivel_cuenta     
    ,cod_producto_nivel_01
    ,cod_producto_nivel_02
    ,cod_producto_nivel_03
    ,cod_producto_nivel_04
    ,cod_producto_nivel_05
    ,cod_producto_nivel_06
    ,cod_producto_nivel_07
    ,sld_actual           
    ,sld_disponible       
    ,cod_sld_disponible   
    ,CURRENT_TIMESTAMP() AS FEC_CARGA            
    ,cod_sistema     
    ,IF(desc_cod_titular='T-TITULAR','T','O') as cod_titular     
FROM ${esquema_cu}.cu_cap_portafolio_cuentas_activas
WHERE cod_estatus != 'CANCELADA'
;

COMPUTE STATS ${esquema_cd}.cd_cap_portafolio_cuentas_activas;
