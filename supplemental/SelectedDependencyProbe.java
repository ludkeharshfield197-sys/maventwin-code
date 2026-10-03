import java.lang.reflect.*;
import java.nio.charset.StandardCharsets;
public final class SelectedDependencyProbe {
  public static void main(String[] args) throws Exception {
    if(args[0].equals("logging")) {
      Class<?> factory=Class.forName("org.apache.commons.logging.LogFactory");
      Class<?> log=Class.forName("org.apache.commons.logging.Log");
      Object value=factory.getMethod("getLog",String.class).invoke(null,"maventwin-probe");
      System.out.println("CHECK logger-created="+(value!=null));
      System.out.println("CHECK info-enabled="+log.getMethod("isInfoEnabled").invoke(value));
      log.getMethod("info",Object.class).invoke(value,"MavenTwin selected dependency probe");
      System.out.println("CHECK info-invoked=true");
      System.out.println("ORIGIN "+factory.getProtectionDomain().getCodeSource().getLocation());
    } else {
      Class<?> buffers=Class.forName("io.netty.buffer.Unpooled");
      Class<?> bytebuf=Class.forName("io.netty.buffer.ByteBuf");
      Object buf=buffers.getMethod("wrappedBuffer",byte[].class).invoke(null,(Object)"MavenTwin".getBytes(StandardCharsets.UTF_8));
      System.out.println("CHECK readable-bytes="+bytebuf.getMethod("readableBytes").invoke(buf));
      System.out.println("CHECK first-byte="+bytebuf.getMethod("readByte").invoke(buf));
      bytebuf.getMethod("release").invoke(buf);
      Class<?> builder=Class.forName("io.netty.handler.ssl.SslContextBuilder");
      Class<?> ssl=Class.forName("io.netty.handler.ssl.SslContext");
      Object context=builder.getMethod("build").invoke(builder.getMethod("forClient").invoke(null));
      Class<?> allocator=Class.forName("io.netty.buffer.ByteBufAllocator");
      Object allocation=Class.forName("io.netty.buffer.UnpooledByteBufAllocator").getField("DEFAULT").get(null);
      javax.net.ssl.SSLEngine engine=(javax.net.ssl.SSLEngine)ssl.getMethod("newEngine",allocator).invoke(context,allocation);
      System.out.println("CHECK client-mode="+engine.getUseClientMode());
      System.out.println("ORIGIN "+builder.getProtectionDomain().getCodeSource().getLocation());
    }
  }
}
