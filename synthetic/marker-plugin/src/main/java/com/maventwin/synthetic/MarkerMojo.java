package com.maventwin.synthetic;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import org.apache.maven.plugin.AbstractMojo;
import org.apache.maven.plugin.MojoExecutionException;
import org.apache.maven.plugins.annotations.LifecyclePhase;
import org.apache.maven.plugins.annotations.Mojo;
import org.apache.maven.plugins.annotations.Parameter;

@Mojo(name="mark", defaultPhase=LifecyclePhase.VALIDATE, threadSafe=true)
public class MarkerMojo extends AbstractMojo {
  @Parameter(defaultValue="${project.basedir}", readonly=true, required=true) private File basedir;
  public void execute() throws MojoExecutionException {
    try { File target=new File(basedir,"target"); target.mkdirs(); Files.write(new File(target,"maventwin-marker.txt").toPath(), "MAVENTWIN_MARKER".getBytes(StandardCharsets.UTF_8)); }
    catch (Exception e) { throw new MojoExecutionException("marker failed",e); }
  }
}
